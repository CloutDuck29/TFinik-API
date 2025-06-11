from fastapi import APIRouter, Depends, HTTPException, Header
from sqlmodel import Session, select
from database import FinancialGoal, get_session
from auth.utils import get_current_user
from pydantic import BaseModel
from datetime import date
from uuid import UUID

router = APIRouter()

class GoalCreate(BaseModel):
    name: str
    target_amount: float
    deadline: date | None = None

class GoalUpdate(BaseModel):
    name: str | None = None
    target_amount: float | None = None
    deadline: date | None = None

class AddAmount(BaseModel):
    amount: float

@router.get("/", response_model=list[FinancialGoal])
def get_goals(session: Session = Depends(get_session), user=Depends(get_current_user)):
    return session.exec(select(FinancialGoal).where(FinancialGoal.user_email == user["email"])).all()

@router.post("/")
def create_goal(data: GoalCreate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    goal = FinancialGoal(
        user_email=user["email"],
        name=data.name,
        target_amount=data.target_amount,
        current_amount=0,
        deadline=data.deadline
    )
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal

@router.patch("/{goal_id}")
def update_goal(goal_id: int, data: GoalUpdate, session: Session = Depends(get_session), user=Depends(get_current_user)):
    goal = session.get(FinancialGoal, goal_id)
    if not goal or goal.user_email != user["email"]:
        raise HTTPException(404, "Цель не найдена")

    if data.name is not None:
        goal.name = data.name
    if data.target_amount is not None:
        goal.target_amount = data.target_amount
    if data.deadline is not None:
        goal.deadline = data.deadline

    session.add(goal)
    session.commit()
    return {"msg": "Цель обновлена"}

@router.post("/{goal_id}/add")
def add_to_goal(goal_id: int, data: AddAmount, session: Session = Depends(get_session), user=Depends(get_current_user)):
    goal = session.get(FinancialGoal, goal_id)
    if not goal or goal.user_email != user["email"]:
        raise HTTPException(404, "Цель не найдена")

    goal.current_amount += data.amount
    session.add(goal)
    session.commit()
    return {"msg": f"Добавлено {data.amount}₽"}
