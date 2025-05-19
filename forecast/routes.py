import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List
from sklearn.linear_model import LinearRegression
from pydantic import BaseModel, Field


router = APIRouter(prefix="/forecast", tags=["Forecast"])

class Transaction(BaseModel):
    date: str
    cost: float
    is_income: bool = Field(..., alias="isIncome")
    category: str
    class Config:
        allow_population_by_field_name = True

class ForecastRequest(BaseModel):
    transactions: List[Transaction]

class CategoryForecastItem(BaseModel):
    category: str
    amount: float

class CategoryForecastResponse(BaseModel):
    month: str
    categories: List[CategoryForecastItem]

@router.post("/")
def get_forecast(req: ForecastRequest):
    try:
        transactions_data = [t.model_dump() for t in req.transactions]
        df = pd.DataFrame(transactions_data)

        if df.empty:
            raise HTTPException(status_code=400, detail="Данные не распарсились — пустой DataFrame")

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df = df[~df['is_income']]
        df = df[~df['category'].isin(["Переводы", "Пополнения"])]

        latest_date = df['date'].max()
        one_year_ago = latest_date - pd.DateOffset(months=12)
        df = df[df['date'] >= one_year_ago]

        if df.empty:
            raise HTTPException(status_code=400, detail="Нет расходов за последние 12 месяцев")

        df['year_month'] = df['date'].dt.to_period('M').astype(str)
        monthly = df.groupby('year_month')['cost'].sum().reset_index()
        monthly['month_index'] = range(len(monthly))

        if len(monthly) < 3:
            raise HTTPException(status_code=400, detail="Недостаточно месяцев для прогноза (нужно ≥ 3)")

        model = LinearRegression()
        X = monthly[['month_index']]
        y = monthly['cost']
        model.fit(X, y)

        future_indexes = np.array([[i] for i in range(len(monthly), len(monthly) + 3)])
        predictions = model.predict(future_indexes)

        last_date = pd.to_datetime(monthly['year_month'].iloc[-1] + "-01")
        future_months = [(last_date + pd.DateOffset(months=i + 1)).strftime("%Y-%m") for i in range(3)]

        result = [{"month": m, "amount": round(a, 2)} for m, a in zip(future_months, predictions)]

        return {"forecast": result}

    except Exception as e:
        print("Ошибка прогноза:", e)
        raise HTTPException(status_code=500, detail=f"Ошибка прогноза: {e}")

@router.post("/categories/", response_model=CategoryForecastResponse)
def forecast_categories(
    month: str = Query(..., description="Месяц в формате YYYY-MM"),
    req: ForecastRequest = Body(...)
):
    try:
        try:
            target_date = pd.to_datetime(month + "-01", format="%Y-%m-%d")
        except Exception:
            raise HTTPException(status_code=400, detail="Неверный формат месяца. Используйте YYYY-MM")

        transactions_data = [t.model_dump() for t in req.transactions]
        df = pd.DataFrame(transactions_data)

        if df.empty:
            raise HTTPException(status_code=400, detail="Данные не распарсились — пустой DataFrame")

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df = df[~df['is_income']]
        df = df[df['cost'] < 0]  # расходы отрицательны
        df = df[~df['category'].isin(["Переводы", "Пополнения"])]

        start_date = target_date - pd.DateOffset(months=12)
        df = df[(df['date'] >= start_date) & (df['date'] < target_date)]

        if df.empty:
            raise HTTPException(status_code=400, detail="Нет расходов для прогноза за указанный период")

        df['year_month'] = df['date'].dt.to_period('M').astype(str)
        monthly_cat = df.groupby(['year_month', 'category'])['cost'].sum().reset_index()

        categories = monthly_cat['category'].unique()

        results = []
        for cat in categories:
            cat_data = monthly_cat[monthly_cat['category'] == cat].copy()
            cat_data = cat_data.sort_values('year_month')
            cat_data['month_index'] = range(len(cat_data))

            if len(cat_data) < 3:
                continue

            X = cat_data[['month_index']]
            y = cat_data['cost']
            model = LinearRegression()
            model.fit(X, y)

            next_month_index = len(cat_data)
            prediction = model.predict([[next_month_index]])[0]

            results.append(CategoryForecastItem(category=cat, amount=prediction))

        if not results:
            raise HTTPException(status_code=400, detail="Недостаточно данных для прогноза по категориям")

        # Сумма прогнозов по категориям
        total_cat_forecast = sum(item.amount for item in results)

        # Общий прогноз за месяц (из общей модели, либо можно посчитать здесь)
        # Для примера возьмем общую сумму расходов за последний год и линейную регрессию
        monthly_total = df.groupby('year_month')['cost'].sum().reset_index()
        monthly_total = monthly_total.sort_values('year_month')
        monthly_total['month_index'] = range(len(monthly_total))
        model_total = LinearRegression()
        model_total.fit(monthly_total[['month_index']], monthly_total['cost'])
        overall_prediction = model_total.predict([[len(monthly_total)]])[0]

        # Коэффициент масштабирования
        if total_cat_forecast != 0:
            scale_factor = overall_prediction / total_cat_forecast
        else:
            scale_factor = 1.0

        # Применяем масштабирование и округляем
        for item in results:
            item.amount = round(item.amount * scale_factor, 2)

        # Сортируем и берем топ-3, как и раньше
        results = sorted(results, key=lambda x: abs(x.amount), reverse=True)[:3]

        return CategoryForecastResponse(month=month, categories=results)

    except Exception as e:
        print("Ошибка прогноза по категориям:", e)
        raise HTTPException(status_code=500, detail=f"Ошибка прогноза по категориям: {e}")
