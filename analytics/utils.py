from datetime import datetime, timedelta, date
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from jose import jwt
from fastapi import HTTPException

SECRET = "supersecretkey"
ALGO = "HS256"

MONTHS_RU = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
    7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек"
}

def decode_token_and_get_email(authorization: str) -> str:
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET, algorithms=[ALGO])
        return payload["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

def generate_category_stats(transactions):
    expenses = defaultdict(float)
    total_spent = 0.0
    dates = []

    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.date, "%d.%m.%Y")
        except ValueError:
            continue

        if tx_date < cutoff or tx.category == "Пополнение" or tx.cost > 0:
            continue

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

def generate_monthly_stats(transactions):
    now = datetime.utcnow()
    six_months_ago = now - relativedelta(months=5)
    start_cutoff = datetime(six_months_ago.year, six_months_ago.month, 1)
    end_cutoff = datetime(now.year, now.month, 28) + relativedelta(day=31)

    monthly_data = defaultdict(lambda: defaultdict(list))

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.date, "%d.%m.%Y")
        except:
            continue

        if tx_date < start_cutoff or tx_date > end_cutoff:
            continue
        if tx.cost > 0 or tx.category == "Пополнение":
            continue

        month_key = tx_date.strftime("%Y-%m")
        monthly_data[month_key][tx.category].append({
            "amount": abs(tx.cost),
            "description": tx.description
        })

    month_keys_ordered = [
        (now - relativedelta(months=i)).strftime("%Y-%m")
        for i in reversed(range(6))
    ]

    result = []
    for month_key in month_keys_ordered:
        if month_key not in monthly_data:
            continue

        year, month = map(int, month_key.split("-"))
        month_label = MONTHS_RU[month]

        for cat, tx_list in monthly_data[month_key].items():
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



def generate_income_stats(transactions):
    now = datetime.utcnow()
    six_months_ago = now - relativedelta(months=5)
    start_cutoff = datetime(six_months_ago.year, six_months_ago.month, 1)
    end_cutoff = datetime(now.year, now.month, 28) + relativedelta(day=31)

    monthly_data = defaultdict(lambda: defaultdict(list))

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.date, "%d.%m.%Y")
        except:
            continue

        if tx_date < start_cutoff or tx_date > end_cutoff:
            continue
        if tx.cost <= 0 or tx.category != "Пополнение":
            continue

        month_key = tx_date.strftime("%Y-%m")
        monthly_data[month_key][tx.category].append({
            "amount": round(tx.cost, 2),
            "description": tx.description
        })

    month_keys_ordered = [
        (now - relativedelta(months=i)).strftime("%Y-%m")
        for i in reversed(range(6))
    ]

    result = []
    for month_key in month_keys_ordered:
        if month_key not in monthly_data:
            continue

        year, month = map(int, month_key.split("-"))
        month_label = MONTHS_RU[month]

        for cat, tx_list in monthly_data[month_key].items():
            for tx in tx_list:
                result.append({
                    "month": month_label,
                    "category": cat,
                    "amount": tx["amount"],
                    "description": tx["description"]
                })

    return result


import random

def generate_monthly_advice(transactions):
    today = date.today()

    first_this_month = today.replace(day=1)
    last_this_month = (first_this_month + relativedelta(months=1)) - timedelta(days=1)

    first_last_month = first_this_month - relativedelta(months=1)
    last_last_month = first_this_month - timedelta(days=1)

    EMOJI_BY_CATEGORY = {
        "Кофейни": "☕️",
        "Магазины": "🛍️",
        "ЖКХ": "💡",
        "Развлечения": "🎬",
        "Доставка": "🍔",
        "Транспорт": "🚌",
        "Другие": "📊"
    }

    sums = {'this': defaultdict(float), 'last': defaultdict(float)}
    total_this = 0

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.date, "%d.%m.%Y").date()
        except ValueError:
            continue

        period = None
        if first_this_month <= tx_date <= last_this_month:
            period = 'this'
        elif first_last_month <= tx_date <= last_last_month:
            period = 'last'

        if not period:
            continue

        category = tx.category or "Другие"
        amount = abs(tx.cost)

        sums[period][category] += amount
        if period == 'this':
            total_this += amount

    advice_list = []
    for cat in set(sums['this']) | set(sums['last']):
        if cat in {"Переводы", "Пополнение"}:
            continue

        amt_this = sums['this'].get(cat, 0)
        amt_last = sums['last'].get(cat, 0)

        if amt_this == 0:
            continue

        change_pct = ((amt_this - amt_last) / amt_last * 100) if amt_last > 0 else 100
        share_pct = amt_this / total_this * 100 if total_this > 0 else 0

        if share_pct < 1:
            continue

        if change_pct > 25 or share_pct > 30:
            phrases = [
                f"Это {share_pct:.0f}% всех расходов — подумайте, нужно ли это.",
                f"Категория заняла {share_pct:.0f}% от всего — может, стоит сократить?",
                f"На это ушло {share_pct:.0f}% от всех трат — подумайте о приоритетах.",
                f"Целых {share_pct:.0f}% расходов! Возможно, стоит пересмотреть это."
            ]
            emoji = EMOJI_BY_CATEGORY.get(cat, "💸")
            advice_text = (
                f"{emoji} Вы тратите на '{cat}' на {change_pct:.0f}% больше, чем в прошлом месяце. "
                + random.choice(phrases)
            )
            advice_list.append({
                "category": cat,
                "change_percent": round(change_pct, 1),
                "share_percent": round(share_pct, 1),
                "advice": advice_text
            })

    advice_list.sort(key=lambda x: x["share_percent"], reverse=True)
    return advice_list

