from sqlmodel import SQLModel, Field, create_engine, Session
from typing import Optional
import datetime


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: str
    time: Optional[str]
    amount: float  # <-- было cost
    description: str
    category: str
    bank: str
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


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
