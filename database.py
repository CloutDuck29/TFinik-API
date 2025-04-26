from sqlmodel import SQLModel, Field, create_engine, Session
from typing import Optional
from datetime import datetime, timedelta


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str
    hashed_password: str

class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    date: str
    time: str | None
    cost: float
    description: str
    category: str
    bank: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_email: str  # <- новый атрибут для БД (чтобы не было шизы)

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
