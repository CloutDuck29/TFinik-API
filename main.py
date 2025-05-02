from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel, EmailStr
from passlib.hash import bcrypt
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse
from sqlmodel import Session
from database import init_db, engine, Transaction as DBTransaction
import os, re, pdfplumber, logging
from collections import defaultdict
import traceback
from sqlmodel import SQLModel
from fastapi import Depends, Header
from jose import jwt
from fastapi import Path
from fastapi.openapi.models import APIKey, APIKeyIn, SecuritySchemeType, SecurityScheme
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer
from fastapi import Request
from database import User as DBUser
from fastapi import Form
from sqlmodel import select
from database import Statement as DBStatement
from collections import defaultdict
from dateutil.relativedelta import relativedelta

# отключаем варнинги
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)


# --- ПАРСИН PDF ---
def parse_statement(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    m = re.search(r'Движение средств за период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})', text)
    start, end = m.groups() if m else (None, None)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    pat1 = re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})\s+([+\-][\d\s\.,]+)\s+₽\s+([+\-][\d\s\.,]+)\s+₽\s+(.+?)\s+(\d{4})$')
    pat2 = re.compile(r'^(\d{2}:\d{2})\s+(\d{2}:\d{2})\s+(.+)$')

    footer_patterns = [
        re.compile(r'^АО «ТБанк', re.IGNORECASE),
        re.compile(r'^БИК', re.IGNORECASE),
        re.compile(r'^ИНН', re.IGNORECASE),
        re.compile(r'^Пополнения[:\s]', re.IGNORECASE),
        re.compile(r'^Расход[:\s]', re.IGNORECASE),
        re.compile(r'^Итого', re.IGNORECASE),
        re.compile(r'^С уважением', re.IGNORECASE),
    ]

    txs = []
    clean = lambda s: float(s.replace(" ", "").replace(",", "."))
    i = 0
    while i < len(lines) - 1:
        m1 = pat1.match(lines[i])
        m2 = pat2.match(lines[i + 1])
        if m1 and m2:
            date_op, _, amt_op_raw, _, desc1, _ = m1.groups()
            time_op, _, desc2 = m2.groups()
            desc = f"{desc1} {desc2}"
            j = i + 2
            while j < len(lines):
                if pat1.match(lines[j]) or pat2.match(lines[j]) or any(p.search(lines[j]) for p in footer_patterns):
                    break
                desc += ' ' + lines[j]
                j += 1
            amount_value = clean(amt_op_raw)
            txs.append({
                'date': date_op,
                'time': time_op,
                'amount': amount_value,
                'description': desc.strip(),
                'isIncome': amount_value > 0
            })
            i = j
        else:
            i += 1

    print(f"✅ Parsed {len(txs)} transactions")
    return start, end, txs


# --- КАТЕГОРИЗАЦИЯ ---
def categorize_by_place(txs):
    rules = {
        'Кофейни':            [r'кофе', r'кофейня', r'кофешоп', r'cafe', r'coffee',
                               r'шоколадница', r'кофемания', r'Coffeemania',
                               r'даблби', r'DBL', r'DoubleB', r'скуратов', r'skuratov',
                               r'энитайм', r'entime', r'starbucks', r'старбакс'],
        'Магазины':           [r'krasnoe', r'красное', r'beloye', r'белое', r'magnit', r'магнит',
                               r'победа', r'pobeda', r'plaza', r'fixprice', r'фикс прайс',
                               r'triumf', r'триумф', r'bufet', r'буфет', r'pek', r'пекарушка',
                               r'prostor', r'простор', r'ozon', r'ozon\.ru', r'wildberries',
                               r'валдберрис', r'avito', r'пят(ё|е)рочка', r'ашан',
                               r'д(и|и)?кси', r'лента', r'okey', r'окей', r'\bip\b',
                                r'ярче!?', r'yarche',
                               r'GLOBUS'
                                r'мария[\s\-]?ра', r'maria[\s\-]?ra',
                                r'монетка', r'monetka',
                                r'командор', r'komandor',
                                r'холидей', r'holiday',
                                r'батон', r'baton',
                                r'аникс', r'aniks',
                                r'слата', r'slata',
                                r'ярмарка',
                                r'континент', r'kontinent',
                                r'пч[её]лка', r'pchelk',
                                r'dns[-\s]?shop', r'\bdns\b',
                                r'citilink', r'ситилинк',
                                r'leroy[\s\-]?merlin', r'леруа',
                                r'\bobi\b', r'оби',
                                r'trial', r'sport'],

        'Транспорт':          ['metro', 'omka', 'омка', 'Transport'],
        'Доставка/Еда':       [r'yandex', r'яндекс', r'eda', r'еда', r'samokat', r'самокат',
                               r'delivery', r'доставка', r'uber', r'ubereats', r'food',
                               r'доставк[ae]', r'деливери'],
        'Развлечения':        [r'ivi', r'okko', r'kinopoisk', r'netflix', r'кинопоиск'],
        'Пополнение':         [r'пополнение', r'внесение наличных', r'cashback', r'кэшбэк'],
        'ЖКХ/Коммуналка':     [r'zhku', r'жкх', r'kvartplata', r'квартплата', r'dsos', r'коммунал'],
        'Переводы':           [r'перевод'],
    }

    regex = {cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in rules.items()}

    for tx in txs:
        tx['category'] = 'Другие'
        for cat, patterns in regex.items():
            if any(p.search(tx['description']) for p in patterns):
                tx['category'] = cat
                break
    return txs


# --- АВТОРИЗАЦИЯ ---
SECRET, ALGO = "supersecretkey", "HS256"
ACCESS_TTL = timedelta(days=30)
users = {}

class Creds(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int

security = HTTPBearer()

# --- FASTAPI ---
app = FastAPI()
def init_db():
    SQLModel.metadata.create_all(engine)

@app.on_event("startup")
def on_startup():
    init_db()

def make_tokens(sub: str):
    now = datetime.utcnow()
    access = jwt.encode({"sub": sub, "exp": now + ACCESS_TTL}, SECRET, ALGO)
    refresh = jwt.encode({"sub": sub, "exp": now + timedelta(days=30)}, SECRET, ALGO)
    return access, refresh

@app.post("/auth/register", status_code=201)
def register(c: Creds):
    with Session(engine) as session:
        existing = session.exec(select(DBUser).where(DBUser.email == c.email)).first()
        if existing:
            raise HTTPException(400, "User exists")
        new_user = DBUser(email=c.email, hashed_password=bcrypt.hash(c.password))
        session.add(new_user)
        session.commit()
    return {"msg": "ok"}


@app.post("/auth/login", response_model=TokenPair)
def login(c: Creds):
    with Session(engine) as session:
        user = session.exec(select(DBUser).where(DBUser.email == c.email)).first()
        if not user or not bcrypt.verify(c.password, user.hashed_password):
            raise HTTPException(401, "Invalid credentials")
        a, r = make_tokens(user.email)
        return {"access_token": a, "refresh_token": r, "expires_in": int(ACCESS_TTL.total_seconds())}

# добавь вот эту функцию
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="TFinik API",
        version="1.0.0",
        description="API для загрузки и анализа банковских транзакций",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/transactions")
async def get_transactions(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    payload = jwt.decode(token, SECRET, algorithms=[ALGO])
    user_email = payload["sub"]

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    return transactions


@app.post("/transactions/upload")
async def upload_statement(
    request: Request,
    file: UploadFile = File(...),
    bank: str = Form(...)
):
    print("upload_statement called")
    print("Uploaded file:", file.filename)
    print("Selected bank:", bank)

    if not file.filename.endswith('.pdf'):
        raise HTTPException(400, detail="Only PDF files are supported.")

    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Authorization header missing or invalid")

    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception as e:
        print("JWT decode failed:", str(e))
        raise HTTPException(401, "Invalid or expired token")

    contents = await file.read()
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, 'wb') as f:
        f.write(contents)

    try:
        start, end, txs = parse_statement(temp_path)
        categorized = categorize_by_place(txs)

        with Session(engine) as session:
            # ⬇ используем переданный банк
            start_date = datetime.strptime(start, "%d.%m.%Y").date()
            end_date = datetime.strptime(end, "%d.%m.%Y").date()

            # Проверяем, есть ли уже такая выписка
            existing_statement = session.exec(
                select(DBStatement).where(
                    (DBStatement.user_email == user_email) &
                    (DBStatement.bank == bank) &
                    (DBStatement.date_start == start_date) &
                    (DBStatement.date_end == end_date)
                )
            ).first()

            if existing_statement:
                raise HTTPException(status_code=400, detail="Такая выписка уже загружена.")

            # Создаём новую, если такой не было
            statement = DBStatement(
                user_email=user_email,
                bank=bank,
                date_start=start_date,
                date_end=end_date
            )
            session.add(statement)
            session.commit()
            session.refresh(statement)

            db_transactions = []
            for tx in categorized:
                tx["bank"] = bank
                tx["cost"] = tx["amount"]

                db_tx = DBTransaction(
                    date=tx["date"],
                    time=tx.get("time"),
                    cost=tx["cost"],
                    description=tx["description"],
                    category=tx["category"],
                    bank=tx["bank"],
                    user_email=user_email,
                    statement_id=statement.id
                )
                session.add(db_tx)
                db_transactions.append(db_tx)

            session.commit()

            response_transactions = []
            for db_tx in db_transactions:
                response_transactions.append({
                    "id": db_tx.id,
                    "date": db_tx.date,
                    "time": db_tx.time,
                    "amount": db_tx.cost,
                    "isIncome": db_tx.cost > 0,
                    "description": db_tx.description,
                    "category": db_tx.category,
                    "bank": db_tx.bank
                })

        return {
            "period": {"start": start, "end": end},
            "transactions": response_transactions
        }

    except HTTPException as http_exc:
        raise http_exc  # пробрасываем как есть, чтобы клиент получил 400
    except Exception as e:
        print("❌ Exception occurred:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.remove(temp_path)


@app.get("/analytics/categories")
async def get_analytics(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception as e:
        raise HTTPException(401, "Invalid or expired token")

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    if not transactions:
        return {
            "totalSpent": 0,
            "period": {"start": None, "end": None},
            "categories": []
        }

    expenses = defaultdict(float)
    total_spent = 0.0
    dates = []

    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.date, "%d.%m.%Y")
        except ValueError:
            continue  # Пропускаем некорректные даты

        if tx_date < cutoff:
            continue  # Пропускаем транзакции старше 30 дней

        if tx.category == "Пополнение" or tx.cost > 0:
            continue  # Пропускаем пополнения и доходы

        expenses[tx.category] += abs(tx.cost)
        total_spent += abs(tx.cost)
        dates.append(tx_date)


    period = {
        "start": min(dates).strftime("%d.%m.%Y") if dates else None,
        "end": max(dates).strftime("%d.%m.%Y") if dates else None
    }

    categories_list = [
        {"category": name, "amount": round(amount, 2)}
        for name, amount in expenses.items()
    ]

    return {
        "totalSpent": round(total_spent, 2),
        "period": period,
        "categories": categories_list
    }


@app.get("/statements")
def get_statements(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    payload = jwt.decode(token, SECRET, algorithms=[ALGO])
    user_email = payload["sub"]

    with Session(engine) as session:
        statements = session.exec(
            select(DBStatement).where(DBStatement.user_email == user_email)
        ).all()

    return [
        {
            "id": s.id,
            "bank": s.bank,
            "date_start": s.date_start.strftime("%d.%m.%Y"),
            "date_end": s.date_end.strftime("%d.%m.%Y"),
            "uploaded_at": s.uploaded_at.isoformat()
        }
        for s in statements
    ]


@app.post("/auth/refresh", response_model=TokenPair)
def refresh_tokens(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired refresh token")

    a, r = make_tokens(user_email)
    return {"access_token": a, "refresh_token": r, "expires_in": int(ACCESS_TTL.total_seconds())}


@app.get("/analytics/monthly")
def get_monthly_analytics(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        user_email = payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    MONTHS_RU = {
        1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
        7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек"
    }

    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month

    if current_month <= 6:
        start_month = 1
        end_month = current_month
    else:
        start_month = current_month
        end_month = 12

    start_cutoff = datetime(current_year, start_month, 1)
    end_cutoff = datetime(current_year, end_month, 28) + relativedelta(day=31)

    with Session(engine) as session:
        transactions = session.exec(
            select(DBTransaction).where(DBTransaction.user_email == user_email)
        ).all()

    monthly_data = defaultdict(lambda: defaultdict(list))  # {month_number: {category: [tx_dicts]}}

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.date, "%d.%m.%Y")
        except:
            continue

        if tx_date < start_cutoff or tx_date > end_cutoff:
            continue

        if tx.cost > 0 or tx.category == "Пополнение":
            continue

        month_number = tx_date.month
        monthly_data[month_number][tx.category].append({
            "amount": abs(tx.cost),
            "description": tx.description
        })

    result = []
    for month_number in range(start_month, end_month + 1):
        if month_number in monthly_data:
            month_label = MONTHS_RU[month_number]
            for cat, tx_list in monthly_data[month_number].items():
                if cat == "Другие":
                    for tx in tx_list:
                        result.append({
                            "month": month_label,
                            "category": cat,
                            "amount": round(tx["amount"], 2),
                            "description": tx["description"]
                        })
                else:
                    total = sum(tx["amount"] for tx in tx_list)
                    result.append({
                        "month": month_label,
                        "category": cat,
                        "amount": round(total, 2)
                    })

    return result


@app.patch("/transactions/{transaction_id}")
async def update_transaction_category(
    transaction_id: int,
    category_update: dict,
    authorization: str = Header(...)
):
    token = authorization.split(" ")[1]
    payload = jwt.decode(token, SECRET, algorithms=[ALGO])
    user_email = payload["sub"]

    new_category = category_update.get("category")
    if not new_category:
        raise HTTPException(400, "Category required")

    with Session(engine) as session:
        transaction = session.get(DBTransaction, transaction_id)
        if not transaction:
            raise HTTPException(404, "Transaction not found")

        if transaction.user_email != user_email:
            raise HTTPException(403, "Forbidden")

        transaction.category = new_category
        session.add(transaction)
        session.commit()

    return {"msg": "Category updated"}
