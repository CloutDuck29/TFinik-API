from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select
from passlib.hash import bcrypt
from database import User as DBUser
from database import engine
from auth.utils import make_tokens
from auth.schemas import TokenPair, Creds
from config import ACCESS_TTL

router = APIRouter()

@router.post("/register", status_code=201)
def register(c: Creds):
    with Session(engine) as session:
        existing = session.exec(select(DBUser).where(DBUser.email == c.email)).first()
        if existing:
            raise HTTPException(400, "User exists")
        new_user = DBUser(email=c.email, hashed_password=bcrypt.hash(c.password))
        session.add(new_user)
        session.commit()
    return {"msg": "ok"}


@router.post("/login", response_model=TokenPair)
def login(c: Creds):
    with Session(engine) as session:
        user = session.exec(select(DBUser).where(DBUser.email == c.email)).first()
        if not user or not bcrypt.verify(c.password, user.hashed_password):
            raise HTTPException(401, "Invalid credentials")
        a, r = make_tokens(user.email)
        return {
            "access_token": a,
            "refresh_token": r,
            "expires_in": int(ACCESS_TTL.total_seconds())
        }



@router.post("/refresh", response_model=TokenPair)
def refresh_tokens(refresh_token: str):
    from auth.utils import decode_token
    user_email = decode_token(refresh_token)
    a, r = make_tokens(user_email)
    return {
        "access_token": a,
        "refresh_token": r,
        "expires_in": int(ACCESS_TTL.total_seconds())
    }
