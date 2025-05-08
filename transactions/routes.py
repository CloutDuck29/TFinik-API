from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, Header, Path
from sqlmodel import Session, select
from database import Transaction as DBTransaction, Statement as DBStatement
from transactions.utils import parse_statement, categorize_by_place
from auth.utils import decode_token
from datetime import datetime
import os, traceback
from database import engine
from fastapi import Depends
from typing import List
from sqlmodel import Session, select
from auth.utils import get_current_user
from database import get_session, Transaction as DBTransaction
from pydantic import BaseModel
from datetime import date




router = APIRouter()

@router.get("/")
def get_transactions(authorization: str = Header(...)):
    user_email = decode_token(authorization.split(" ")[1])
    with Session(engine) as session:
        return session.exec(select(DBTransaction).where(DBTransaction.user_email == user_email)).all()


@router.post("/upload")
async def upload_statement(
    request: Request,
    file: UploadFile = File(...),
    bank: str = Form(...)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    user_email = decode_token(request.headers.get("authorization").split(" ")[1])
    contents = await file.read()
    temp_path = f"/tmp/{file.filename}"

    with open(temp_path, 'wb') as f:
        f.write(contents)

    try:
        start, end, txs = parse_statement(temp_path)
        if not txs:
            return {"period": {"start": start, "end": end}, "transactions": []}

        categorized = categorize_by_place(txs)

        with Session(engine) as session:
            start_date = datetime.strptime(start, "%d.%m.%Y").date()
            end_date = datetime.strptime(end, "%d.%m.%Y").date()

            # Проверка дубликатов
            existing = session.exec(
                select(DBStatement).where(
                    (DBStatement.user_email == user_email) &
                    (DBStatement.bank == bank) &
                    (DBStatement.date_start == start_date) &
                    (DBStatement.date_end == end_date)
                )
            ).first()
            if existing:
                raise HTTPException(400, "Такая выписка уже загружена.")

            statement = DBStatement(
                user_email=user_email,
                bank=bank,
                date_start=start_date,
                date_end=end_date
            )
            session.add(statement)
            session.commit()
            session.refresh(statement)

            # Сохраняем транзакции
            for tx in categorized:
                tx_obj = DBTransaction(
                    date=tx["date"],
                    time=tx.get("time"),
                    cost=tx["amount"],
                    description=tx["description"],
                    category=tx["category"],
                    bank=bank,
                    user_email=user_email,
                    statement_id=statement.id
                )
                session.add(tx_obj)

            session.commit()

            # Сборка ответа с id
            transactions = session.exec(
                select(DBTransaction).where(DBTransaction.statement_id == statement.id)
            ).all()

            response_transactions = [{
                "id": tx.id,
                "date": tx.date,
                "time": tx.time,
                "amount": tx.cost,
                "isIncome": tx.cost > 0,
                "description": tx.description,
                "category": tx.category,
                "bank": tx.bank
            } for tx in transactions]

        return {
            "period": {"start": start, "end": end},
            "transactions": response_transactions
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        os.remove(temp_path)



@router.patch("/{transaction_id}")
def update_transaction_category(
    transaction_id: int = Path(...),
    category_update: dict = {},
    authorization: str = Header(...)
):
    user_email = decode_token(authorization.split(" ")[1])
    new_category = category_update.get("category")
    if not new_category:
        raise HTTPException(400, "Category required")

    with Session(engine) as session:

        tx = session.get(DBTransaction, transaction_id)
        if not tx:
            raise HTTPException(404, "Transaction not found")
        if tx.user_email != user_email:
            raise HTTPException(403, "Forbidden")
        tx.category = new_category
        session.add(tx)
        session.commit()
    return {"msg": "Category updated"}

class TransactionOut(BaseModel):
    id: int
    date: date
    amount: float
    description: str
    category: str
    bank: str
    isIncome: bool

def parse_date(date_str: str):
    return datetime.strptime(date_str, "%d.%m.%Y").date()

@router.get("/history", response_model=List[TransactionOut])
def get_transaction_history(
    session: Session = Depends(get_session),
    user: dict = Depends(get_current_user)
):
    transactions = session.exec(
        select(DBTransaction)
        .where(DBTransaction.user_email == user["email"])
        .order_by(DBTransaction.date.desc())
    ).all()

    return [
        TransactionOut(
            id=tx.id,
            date=parse_date(tx.date),  # ← ПАРСИМ строку в datetime.date
            amount=tx.cost,
            description=tx.description,
            category=tx.category,
            bank=tx.bank,
            isIncome=tx.cost > 0
        )
        for tx in transactions
    ]