from fastapi import APIRouter, Header, HTTPException
from sqlmodel import Session, select
from database import engine, Transaction as DBTransaction
from jose import jwt
from datetime import datetime, timedelta, date
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from analytics.utils import generate_category_stats, generate_monthly_stats, generate_income_stats, generate_monthly_advice

router = APIRouter()

SECRET, ALGO = "supersecretkey", "HS256"

@router.get("/analytics/categories")
def get_category_analytics(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    return generate_category_stats(transactions)


@router.get("/analytics/monthly")
def get_monthly_analytics(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    return generate_monthly_stats(transactions)


@router.get("/analytics/income")
def get_monthly_income(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    return generate_income_stats(transactions)


@router.get("/advice/monthly")
def monthly_advice(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    return generate_monthly_advice(transactions)
