from sqlmodel import SQLModel, Field, create_engine, Session
from typing import Optional
from datetime import datetime, date
from uuid import uuid4, UUID

# Модель пользователя
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
    user_email: str
    statement_id: Optional[int] = Field(default=None, foreign_key="statement.id")

# ✅ Новая модель — загруженные выписки
class Statement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_email: str
    bank: str
    date_start: date
    date_end: date
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

class FinancialGoal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: UUID = Field(default_factory=uuid4, index=True)
    user_email: str
    name: str
    target_amount: float
    current_amount: float
    deadline: Optional[date]

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
