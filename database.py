from sqlmodel import SQLModel, Field, create_engine, Session
from typing import Optional
from datetime import datetime, timedelta


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    date: str
    time: str | None
    cost: float  # <-- ВАЖНО
    description: str
    category: str
    bank: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Настройка подключения к SQLite (пока локально)
DATABASE_URL = "sqlite:///./transactions.db"
engine = create_engine(DATABASE_URL, echo=False)


# Функция инициализации базы данных (создание таблиц)
def init_db():
    SQLModel.metadata.create_all(engine)


# Пример использования сессии
def get_session():
    with Session(engine) as session:
        yield session
