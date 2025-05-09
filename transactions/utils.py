import re, pdfplumber, logging
from collections import defaultdict

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