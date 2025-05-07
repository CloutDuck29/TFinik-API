from fastapi import APIRouter, Header, HTTPException, Query
from sqlmodel import Session, select
from database import engine, Transaction as DBTransaction
from jose import jwt
from datetime import date
from database import engine


from portrait.utils import portrait_of_month, cluster_days

router = APIRouter()
SECRET = "supersecretkey"
ALGO = "HS256"

@router.get("/portrait")
def get_month_portrait(
    authorization: str = Header(...),
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=2000, le=2100)
):
    # Декодирование токена
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    # Если не указаны — берем текущий месяц и год
    if month is None or year is None:
        today = date.today()
        month = today.month
        year = today.year

    # Загружаем все транзакции пользователя
    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    # Генерируем портрет и денежные паттерны
    portrait = portrait_of_month(transactions, month=month, year=year)
    patterns = cluster_days(transactions, month=month, year=year)

    return {
        "portrait": portrait,
        "patterns": patterns
    }
