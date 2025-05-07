from fastapi import FastAPI
from database import init_db
from auth.routes import router as auth_router
from analytics.routes import router as analytics_router
from transactions.routes import router as transactions_router
from portrait.routes import router as portrait_router
from statements.routes import router as statements_router

app = FastAPI()

from database import init_db

@app.on_event("startup")
def on_startup():
    init_db()


# Регистрация роутеров
app.include_router(auth_router, prefix="/auth")
app.include_router(analytics_router)
app.include_router(transactions_router, prefix="/transactions")
app.include_router(portrait_router)
app.include_router(statements_router)
