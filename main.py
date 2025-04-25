from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from passlib.hash import bcrypt
from jose import jwt
from datetime import datetime, timedelta
from fastapi import UploadFile, File
from fastapi.responses import JSONResponse
import os
import re
import pdfplumber
import logging
from collections import defaultdict
from database import init_db
from sqlmodel import Session
from database import engine, Transaction as DBTransaction



# отключаем варнинги
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)


def parse_statement(pdf_path):
    """Чтение PDF и парсинг транзакций с поддержкой многострочных описаний и извлечением периода"""
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    # Извлекаем период
    m = re.search(r'Движение средств за период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})', text)
    start, end = m.groups() if m else (None, None)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    pat1 = re.compile(
        r'^(\d{2}\.\d{2}\.\d{4})\s+'            # дата операции
        r'(\d{2}\.\d{2}\.\d{4})\s+'             # дата списания
        r'([+\-][\d\s\.,]+)\s+₽\s+'             # сумма операции
        r'([+\-][\d\s\.,]+)\s+₽\s+'             # сумма в валюте карты
        r'(.+?)\s+'                             # часть описания 1
        r'(\d{4})$'                             # последние 4 цифры карты
    )
    pat2 = re.compile(
        r'^(\d{2}:\d{2})\s+'                    # время операции
        r'(\d{2}:\d{2})\s+'                     # время списания
        r'(.+)$'                                # часть описания 2
    )
    footer_patterns = [
        re.compile(r'^АО «ТБанк', re.IGNORECASE),
        re.compile(r'^БИК', re.IGNORECASE),
        re.compile(r'^ИНН', re.IGNORECASE),
        # новые маркеры конца выписки
        re.compile(r'^Пополнения[:\s]', re.IGNORECASE),
        re.compile(r'^Расходы[:\s]', re.IGNORECASE),
        re.compile(r'^Итого', re.IGNORECASE),
        re.compile(r'^С уважением', re.IGNORECASE),
    ]

    txs = []
    i = 0
    clean = lambda s: float(s.replace(" ", "").replace(",", "."))
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
            txs.append({'date': date_op,
                'time': time_op,
                'amount': amount_value,
                'description': desc.strip(),
                'isIncome': amount_value > 0})

            i = j
        else:
            i += 1
    return start, end, txs


def categorize_by_place(txs):
    """Категоризация транзакций по месту операции"""
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
                                r'\bobi\b', r'оби'],

        'Транспорт':          ['metro', 'omka', 'омка'],
        'Доставка/Еда':       [r'yandex', r'яндекс', r'eda', r'еда', r'samokat', r'самокат',
                               r'delivery', r'доставка', r'uber', r'ubereats', r'food',
                               r'доставк[ae]', r'деливери'],
        'Развлечения':        [r'ivi', r'okko', r'kinopoisk', r'netflix', r'кинопоиск'],
        'Пополнение':         [r'пополнение', r'внесение наличных', r'cashback', r'кэшбэк'],
        'ЖКХ/Коммуналка':     [r'zhku', r'жкх', r'kvartplata', r'квартплата', r'dsos', r'коммунал'],
        'Переводы':           [r'перевод'],
    }
    regex = {cat: [re.compile(p, re.IGNORECASE) for p in pats]
             for cat, pats in rules.items()}

    for tx in txs:
        tx['category'] = 'Другие'
        for cat, patterns in regex.items():
            if any(p.search(tx['description']) for p in patterns):
                tx['category'] = cat
                break
    return txs

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

@app.on_event("startup")
def on_startup():
    init_db()

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

@app.post("/transactions/upload")
async def upload_statement(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, 'wb') as f:
        f.write(contents)

    try:
        start, end, txs = parse_statement(temp_path)
        categorized = categorize_by_place(txs)

        # Добавляем поле bank в каждую транзакцию
        for tx in categorized:
            tx["bank"] = "Tinkoff"  # Пока просто хардкодим, потом будет определяться
            tx["isIncome"] = tx.get("isIncome", False)  # если вдруг потеряется


        return {"period": {"start": start, "end": end}, "transactions": categorized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.remove(temp_path)




