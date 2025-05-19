from datetime import datetime, date, timedelta
from calendar import monthrange
from collections import defaultdict, Counter
import numpy as np
from sklearn.cluster import KMeans
from pydantic import BaseModel

MOOD_BY_CATEGORY = {
    'Кофейни':        ('☕️', 'Беззаботный'),
    'Доставка':       ('🍔', 'Спонтанный'),
    'Магазины':       ('🛍️', 'Практичный'),
    'Развлечения':    ('🎬', 'Расслабленный'),
    'ЖКХ':            ('📉', 'Сдержанный'),
    'Пополнение':     ('💰', 'Сберегательный'),
    'Другие':         ('📊', 'Уравновешенный'),
}

PORTRAIT_BLACKLIST = {'Переводы', 'Пополнение'}

class Transaction(BaseModel):
    date: str
    cost: float
    category: str

def safe_parse_date(date_str: str) -> datetime.date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"⛔ Неподдерживаемый формат даты: {date_str}")

def portrait_of_month(transactions, month: int, year: int):
    first_day = date(year, month, 1)
    last_day = first_day.replace(day=monthrange(year, month)[1])

    tx_objects = [Transaction(**tx) if isinstance(tx, dict) else tx for tx in transactions]

    months = ["январь", "февраль", "март", "апрель", "май", "июнь",
              "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    month_name = months[month - 1].capitalize()

    month_txs = [
        tx for tx in tx_objects
        if first_day <= safe_parse_date(tx.date) <= last_day
        and tx.category not in PORTRAIT_BLACKLIST
    ]

    print(f"🔍 Портрет за {month}.{year}, транзакций: {len(tx_objects)}")

    for tx in tx_objects:
        try:
            parsed_date = safe_parse_date(tx.date)
            if first_day <= parsed_date <= last_day:
                print(f"✅ {tx.date} -> ok | {tx.category} | {tx.cost}")
        except Exception as e:
            print(f"❌ {tx.date} -> ошибка парсинга: {e}")

    if not month_txs:
        return {"status": "no_data", "message": f"⚪️ {month_name} — нет расходов для анализа"}

    sums = defaultdict(float)
    counts = Counter()
    for tx in month_txs:
        sums[tx.category] += abs(tx.cost)
        counts[tx.category] += 1

    total = sum(sums.values())
    top_cat = max(sums, key=sums.get)
    share = sums[top_cat] / total
    is_balanced = share < 0.5

    top3 = [cat for cat, _ in counts.most_common(3)]
    emoji, mood = ('📊', 'Уравновешенный')
    for cat in top3:
        if cat in MOOD_BY_CATEGORY:
            emoji, mood = MOOD_BY_CATEGORY[cat]
            break

    return {
        "month": month_name,
        "year": year,
        "status": "ok",
        "balanced": is_balanced,
        "top_categories": top3,
        "emoji": emoji,
        "mood": mood,
        "summary": f"{emoji} {month_name} — {'сбалансированный' if is_balanced else 'разбалансированный'} месяц. "
                   f"Топ категории: {', '.join(top3)}. Настроение: {mood}."
    }

def cluster_days(transactions, month: int, year: int):
    first_day = date(year, month, 1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    daily = defaultdict(float)

    tx_objects = [Transaction(**tx) if isinstance(tx, dict) else tx for tx in transactions]

    for tx in tx_objects:
        try:
            tx_date = safe_parse_date(tx.date)
        except:
            continue
        if first_day <= tx_date <= last_day and tx.category not in PORTRAIT_BLACKLIST:
            daily[tx_date] += abs(tx.cost)

    if not daily:
        return []

    X = np.array([[v] for v in daily.values()])
    k = min(3, len(X))
    km = KMeans(n_clusters=k, n_init="auto", random_state=42).fit(X)

    order = np.argsort(km.cluster_centers_.ravel())
    relabel = {old: new for new, old in enumerate(order)}

    clusters = defaultdict(list)
    for (d, amt), lbl in zip(daily.items(), km.labels_):
        clusters[relabel[lbl]].append((d, amt))

    centers = km.cluster_centers_.ravel()[order]
    names = ['Экономные', 'Сбалансированные', 'Щедрые']
    result = []

    for idx in sorted(clusters):
        days = clusters[idx]
        label = names[idx] if idx < len(names) else f'Тип {idx + 1}'
        limit = centers[idx]
        weekday_count = sum(1 for d, _ in days if d.weekday() < 5)
        weekend_count = len(days) - weekday_count

        result.append({
            "label": label,
            "limit": round(limit, 2),
            "days_total": len(days),
            "weekdays": weekday_count,
            "weekends": weekend_count
        })

    return result
