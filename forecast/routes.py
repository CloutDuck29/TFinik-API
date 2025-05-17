import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/forecast", tags=["Forecast"])

class Transaction(BaseModel):
    date: str
    cost: float
    is_income: bool

@router.post("/")
def get_forecast(transactions: List[Transaction]):
    try:
        df = prepare_monthly_expenses([t.dict() for t in transactions])
        if len(df) < 3:
            raise HTTPException(status_code=400, detail="Недостаточно данных для прогноза")
        result = forecast_next_3_months(df)
        return {"forecast": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def prepare_monthly_expenses(transactions: list):
    df = pd.DataFrame(transactions)
    df['date'] = pd.to_datetime(df['date'])
    df['year_month'] = df['date'].dt.to_period('M').astype(str)
    df = df[~df['is_income']]  # только расходы
    monthly = df.groupby('year_month')['cost'].sum().reset_index()

    monthly['month_index'] = range(len(monthly))  # 0, 1, 2...
    return monthly

def forecast_next_3_months(monthly_df: pd.DataFrame):
    model = LinearRegression()
    X = monthly_df[['month_index']]
    y = monthly_df['cost']
    model.fit(X, y)

    future_indexes = np.array([[i] for i in range(len(monthly_df), len(monthly_df) + 3)])
    predictions = model.predict(future_indexes)

    last_date = pd.to_datetime(monthly_df['year_month'].iloc[-1] + "-01")
    future_months = [(last_date + pd.DateOffset(months=i+1)).strftime("%B") for i in range(3)]

    return [{"month": m, "amount": round(a, 2)} for m, a in zip(future_months, predictions)]
