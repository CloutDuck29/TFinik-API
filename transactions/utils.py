import re, pdfplumber, logging
import datetime

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

# --- ПАРСЕР Т-БАНКА ---
def parse_tbank_statement(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    if not re.search(r'Т-?банк', text, re.IGNORECASE):
        raise ValueError("❌ Файл не является выпиской Т-банка")

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
            is_income = amount_value > 0

            txs.append({
                'date': date_op,
                'time': time_op,
                'amount': amount_value if is_income else -abs(amount_value),  # ✅
                'description': desc.strip(),
                'isIncome': is_income
            })
            i = j
        else:
            i += 1

    return start, end, categorize_tbank(txs)

def categorize_tbank(txs):
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
        'Доставка':       [r'yandex', r'яндекс', r'eda', r'еда', r'samokat', r'самокат',
                               r'delivery', r'доставка', r'uber', r'ubereats', r'food',
                               r'доставк[ae]', r'деливери'],
        'Развлечения':        [r'ivi', r'okko', r'kinopoisk', r'netflix', r'кинопоиск'],
        'Пополнение':         [r'пополнение', r'внесение наличных', r'cashback', r'кэшбэк'],
        'ЖКХ':     [r'zhku', r'жкх', r'kvartplata', r'квартплата', r'dsos', r'коммунал'],
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

# --- ПАРСЕР СБЕРБАНКА ---
def parse_sber_statement(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        texts = [page.extract_text() for page in pdf.pages if page.extract_text()]
        full_text = "\n".join(texts)
        lowered_full = full_text.lower()
        first_page = texts[0].lower() if texts else ""

    if any(foreign in first_page for foreign in ["тинькофф", "tinkoff", "т-банк", "t-bank"]):
        raise ValueError("❌ Это не выписка Сбербанка (обнаружен другой банк в заголовке)")

    sber_ok = any(p in first_page for p in [
        "сбербанк", "выписка по счету", "дебетовая карта", "итого по операциям"
    ])
    if not sber_ok:
        raise ValueError("❌ Это не выписка Сбербанка (не найдено характерных признаков)")


    m = re.search(r'Итого по операциям с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})', full_text)
    if not m:
        m = re.search(r'Движение средств за период с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4})', full_text)
    start, end = m.groups() if m else (None, None)

    lines = full_text.split('\n')
    operation_lines = [line.strip() for line in lines if re.match(r"\d{2}\.\d{2}\.\d{4}", line.strip())]

    transactions = []
    for line in operation_lines:
        match = re.match(r"(\d{2}\.\d{2}\.\d{4})\s+\d{2}:\d{2}\s+\d+\s+(.*?)\s+([+\-]?\d[\d\s\xa0]*,\d{2})", line)
        if match:
            date, description, raw_amount = match.groups()
            clean_str = raw_amount.replace("\xa0", "").replace(" ", "").replace(",", ".")
            amount_value = float(clean_str.lstrip("+-"))

            is_income = raw_amount.strip().startswith("+")
            signed_amount = amount_value if is_income else -amount_value

            transactions.append({
                "date": datetime.datetime.strptime(date, "%d.%m.%Y").date().isoformat(),
                "time": None,
                "amount": signed_amount,
                "description": description.strip(),
                "isIncome": is_income
            })
    return start, end, categorize_sber(transactions)


def categorize_sber(txs):
    mapping = {
        "внесение наличных": "Пополнение",
        "прочие операции": "Переводы",
        "перевод на карту": "Переводы",
        "перевод физическому лицу": "Переводы",
        "перевод СБП": "Переводы",
        "оплата по реквизитам": "Переводы",
        "перевод с карты": "Переводы",
        "отдых и развлечения": "Развлечения",
        "транспорт": "Транспорт",
        "магазин": "Магазины",
        "кафе": "Кофейни",
        "ресторан": "Кофейни",
        "кофейня": "Кофейни",
        "доставка": "Доставка",
        "яндекс еда": "Доставка",
        "delivery": "Доставка",
        "жку": "ЖКХ",
    }

    def remap(description: str) -> str:
        desc = description.lower()
        for key in mapping:
            if key in desc:
                return mapping[key]
        return "Другие"

    for tx in txs:
        tx['category'] = remap(tx['description'])
    return txs

def parse_statement(pdf_path, bank: str):
    bank = bank.lower()
    if bank in ("tinkoff", "tbank"):
        return parse_tbank_statement(pdf_path)
    elif bank == "sber":
        return parse_sber_statement(pdf_path)
    else:
        raise ValueError(f"❌ Unsupported bank: {bank}")
