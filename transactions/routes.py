from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, Header, Path
from sqlmodel import Session, select
from database import Transaction as DBTransaction, Statement as DBStatement
from transactions.utils import parse_statement, categorize_sber, categorize_tbank
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
        start, end, txs = parse_statement(temp_path, bank)
        if not txs:
            return {"period": {"start": start, "end": end}, "transactions": []}

        with Session(engine) as session:
            if not start or not end:
                raise HTTPException(400, detail="Не удалось определить период выписки. Проверь формат PDF.")

            try:
                start_date = datetime.strptime(start, "%d.%m.%Y").date()
                end_date = datetime.strptime(end, "%d.%m.%Y").date()
            except ValueError:
                raise HTTPException(400, detail="Некорректный формат даты в выписке.")

            # --- Проверка: уже есть выписка с этим периодом?
            existing_statement = session.exec(
                select(DBStatement).where(
                    (DBStatement.user_email == user_email) &
                    (DBStatement.bank == bank) &
                    (DBStatement.date_start == start_date) &
                    (DBStatement.date_end == end_date)
                )
            ).first()

            if existing_statement:
                duplicate_count = 0
                for tx in txs:
                    exists = session.exec(
                        select(DBTransaction).where(
                            (DBTransaction.user_email == user_email) &
                            (DBTransaction.date == tx["date"]) &
                            (DBTransaction.cost == tx["amount"]) &
                            (DBTransaction.description == tx["description"]) &
                            (DBTransaction.bank == bank)
                        )
                    ).first()
                    if exists:
                        duplicate_count += 1

                if duplicate_count == len(txs):
                    raise HTTPException(400, detail="Такая выписка уже загружена.")

            # --- Создание новой записи о выписке
            statement = DBStatement(
                user_email=user_email,
                bank=bank,
                date_start=start_date,
                date_end=end_date
            )
            session.add(statement)
            session.commit()
            session.refresh(statement)

            inserted_transactions = []
            for tx in txs:
                exists = session.exec(
                    select(DBTransaction).where(
                        (DBTransaction.user_email == user_email) &
                        (DBTransaction.date == tx["date"]) &
                        (DBTransaction.cost == tx["amount"]) &
                        (DBTransaction.description == tx["description"]) &
                        (DBTransaction.bank == bank)
                    )
                ).first()

                if exists:
                    continue

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
                inserted_transactions.append(tx_obj)

            session.commit()

            response_transactions = [{
                "id": tx.id,
                "date": tx.date,
                "time": tx.time,
                "amount": tx.cost,
                "isIncome": tx.cost > 0,
                "description": tx.description,
                "category": tx.category,
                "bank": tx.bank
            } for tx in inserted_transactions]

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

        # ✅ Обновляем категорию
        tx.category = new_category

        # ✅ Автообработка суммы при смене категории
        if new_category == "Пополнение" and tx.cost < 0:
            tx.cost = abs(tx.cost)
        # ❗️(Опционально) для прочих категорий — делаем сумму отрицательной, если она положительная
        elif new_category != "Пополнение" and tx.cost > 0:
            tx.cost = -abs(tx.cost)

        session.add(tx)
        session.commit()

    return {"msg": "Category and amount updated accordingly"}

class TransactionOut(BaseModel):
    id: int
    date: date
    amount: float
    description: str
    category: str
    bank: str
    isIncome: bool

def parse_date(date_str: str) -> datetime.date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"⛔ Невозможно распарсить дату: {date_str}")


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