import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from sklearn.linear_model import LinearRegression

router = APIRouter(prefix="/forecast", tags=["Forecast"])

# Модель одной транзакции
class Transaction(BaseModel):
    date: str
    cost: float
    is_income: bool
    category: str  # 👈 добавлено для фильтрации

# Обёртка для запроса
class ForecastRequest(BaseModel):
    transactions: List[Transaction]

@router.post("/")
def get_forecast(req: ForecastRequest):
    try:
        # 🔍 Отладка: печать входящих данных
        print(">>> forecast request (raw):", req.transactions)
        transactions_data = [t.model_dump() for t in req.transactions]
        print(">>> forecast request (dicts):", transactions_data)

        df = pd.DataFrame(transactions_data)

        if df.empty:
            raise HTTPException(status_code=400, detail="Данные не распарсились — пустой DataFrame")

        df['date'] = pd.to_datetime(df['date'])
        df = df[~df['is_income']]  # исключаем доходы

        # ⛔ Исключаем переводы и пополнения
        df = df[~df['category'].isin(["Переводы", "Пополнения"])]

        if df.empty:
            raise HTTPException(status_code=400, detail="Нет расходов для прогноза после фильтрации")

        df['year_month'] = df['date'].dt.to_period('M').astype(str)
        monthly = df.groupby('year_month')['cost'].sum().reset_index()
        monthly['month_index'] = range(len(monthly))

        if len(monthly) < 3:
            raise HTTPException(status_code=400, detail="Недостаточно данных для прогноза")

        model = LinearRegression()
        X = monthly[['month_index']]
        y = monthly['cost']
        model.fit(X, y)

        future_indexes = np.array([[i] for i in range(len(monthly), len(monthly) + 3)])
        predictions = model.predict(future_indexes)

        last_date = pd.to_datetime(monthly['year_month'].iloc[-1] + "-01")
        future_months = [(last_date + pd.DateOffset(months=i + 1)).strftime("%B") for i in range(3)]

        result = [{"month": m, "amount": round(a, 2)} for m, a in zip(future_months, predictions)]

        return {"forecast": result}
    except Exception as e:
        print(">>> Ошибка прогноза:", str(e))
        raise HTTPException(status_code=500, detail=f"Ошибка прогноза: {str(e)}")
