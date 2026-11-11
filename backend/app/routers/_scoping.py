from typing import Optional, TypeVar
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.news import Category

T = TypeVar("T")


def get_owned_or_404(db: Session, model: type[T], obj_id: int, household_id: int, label: str = "Item") -> T:
    """Fetches a row by id only if it belongs to the household. Other households'
    rows are indistinguishable from missing ones (404 Not Found)."""
    obj = db.query(model).filter(model.id == obj_id, model.household_id == household_id).first()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def ensure_category(db: Session, category_id: Optional[int], household_id: int) -> None:
    if category_id is not None:
        get_owned_or_404(db, Category, category_id, household_id, "Category")
