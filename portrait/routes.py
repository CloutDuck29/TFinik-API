from fastapi import APIRouter, Header, HTTPException, Query
from sqlmodel import Session, select
from database import engine, Transaction as DBTransaction
from jose import jwt
from datetime import date

from portrait.utils import portrait_of_month, cluster_days, Transaction as PTransaction

router = APIRouter()
SECRET = "supersecretkey"
ALGO = "HS256"

@router.get("/portrait")
def get_month_portrait(
    authorization: str = Header(...),
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=2000, le=2100)
):
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if month is None or year is None:
        today = date.today()
        month = today.month
        year = today.year

    with Session(engine) as session:
        db_transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    transactions = [
        PTransaction(
            date=tx.date,
            cost=tx.cost,
            category=tx.category
        ) for tx in db_transactions
    ]

    portrait = portrait_of_month(transactions, month=month, year=year)
    patterns = cluster_days(transactions, month=month, year=year)

    return {
        "portrait": portrait,
        "patterns": patterns
    }
