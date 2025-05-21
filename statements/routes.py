from fastapi import APIRouter, Header, HTTPException
from sqlmodel import Session, select
from database import engine, Statement as DBStatement
from jose import jwt
from database import engine

router = APIRouter()
SECRET = "supersecretkey"
ALGO = "HS256"

@router.get("/statements")
def get_statements(authorization: str = Header(...)):
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    with Session(engine) as session:
        statements = session.exec(
            select(DBStatement).where(DBStatement.user_email == user_email)
        ).all()

    return [
        {
            "id": s.id,
            "bank": s.bank.lower(),
            "date_start": s.date_start.strftime("%d.%m.%Y"),
            "date_end": s.date_end.strftime("%d.%m.%Y"),
            "uploaded_at": s.uploaded_at.isoformat()
        }
        for s in statements
    ]
