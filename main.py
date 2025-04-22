from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from passlib.hash import bcrypt
from jose import jwt
from datetime import datetime, timedelta

SECRET, ALGO = "supersecretkey", "HS256"
ACCESS_TTL = timedelta(minutes=30)
users = {}

class Creds(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int

app = FastAPI()

def make_tokens(sub: str):
    now = datetime.utcnow()
    access = jwt.encode({"sub":sub, "exp":now+ACCESS_TTL}, SECRET, ALGO)
    refresh = jwt.encode({"sub":sub, "exp":now+ACCESS_TTL*2}, SECRET, ALGO)
    return access, refresh

@app.post("/auth/register", status_code=201)
def register(c: Creds):
    if c.email in users:
        raise HTTPException(400, "User exists")
    users[c.email] = bcrypt.hash(c.password)
    return {"msg":"ok"}

@app.post("/auth/login", response_model=TokenPair)
def login(c: Creds):
    h = users.get(c.email)
    if not h or not bcrypt.verify(c.password, h):
        raise HTTPException(401, "Invalid credentials")
    a, r = make_tokens(c.email)
    return {"access_token":a, "refresh_token":r, "expires_in":int(ACCESS_TTL.total_seconds())}
