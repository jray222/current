"""User and household preferences: crawl schedules, AI categorization, and interest learning controls.
"""
import re
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.household import Household
from app.models.news import InterestModel
from app.services import crawl_schedule
from app.services import interest

router = APIRouter(prefix="/settings", tags=["user_settings"])


class CrawlSettingsRead(BaseModel):
    crawl_enabled: bool
    crawl_time: str
    crawl_every_hours: int
    crawl_every_hours_choices: list[int]
    times: list[str]
    ai_categorize: bool
    crawl_handled_at: Optional[str]


class CrawlSettingsUpdate(BaseModel):
    crawl_enabled: Optional[bool] = None
    crawl_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    crawl_every_hours: Optional[int] = None
    ai_categorize: Optional[bool] = None


class LearningSettingsRead(BaseModel):
    n_votes: int
    bias: float
    top_interests: list[tuple[str, float]]
    muted_terms: list[str]


class FeedSettingsRead(BaseModel):
    category_order: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    preview_lines: int = 2


class FeedSettingsUpdate(BaseModel):
    category_order: Optional[list[str]] = None
    excluded_categories: Optional[list[str]] = None
    preview_lines: Optional[int] = Field(None, ge=0, le=4)


class MuteTermPayload(BaseModel):
    term: str = Field(..., min_length=1, max_length=100)


@router.get("/crawl", response_model=CrawlSettingsRead)
def get_crawl_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    household = db.get(Household, user.household_id)
    if not household:
        raise HTTPException(status_code=404, detail="Household not found")

    start_min = crawl_schedule.parse_time_to_minutes(household.crawl_time or "06:00")
    every = household.crawl_every_hours if household.crawl_every_hours in crawl_schedule.EVERY_HOURS else 24
    mins = crawl_schedule.times_of_day(start_min, every)
    times_str = [f"{m // 60:02d}:{m % 60:02d}" for m in mins]

    return CrawlSettingsRead(
        crawl_enabled=bool(household.crawl_enabled),
        crawl_time=household.crawl_time or "06:00",
        crawl_every_hours=every,
        crawl_every_hours_choices=list(crawl_schedule.EVERY_HOURS),
        times=times_str,
        ai_categorize=bool(household.ai_categorize),
        crawl_handled_at=household.crawl_handled_at.isoformat() if household.crawl_handled_at else None,
    )


@router.patch("/crawl", response_model=CrawlSettingsRead)
def update_crawl_settings(
    payload: CrawlSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    household = db.get(Household, user.household_id)
    if not household:
        raise HTTPException(status_code=404, detail="Household not found")

    if payload.crawl_enabled is not None:
        household.crawl_enabled = 1 if payload.crawl_enabled else 0

    if payload.crawl_time is not None:
        household.crawl_time = payload.crawl_time

    if payload.crawl_every_hours is not None:
        if payload.crawl_every_hours not in crawl_schedule.EVERY_HOURS:
            raise HTTPException(status_code=400, detail=f"crawl_every_hours must be one of {crawl_schedule.EVERY_HOURS}")
        household.crawl_every_hours = payload.crawl_every_hours

    if payload.ai_categorize is not None:
        household.ai_categorize = 1 if payload.ai_categorize else 0

    db.commit()
    return get_crawl_settings(user, db)


@router.get("/learning", response_model=LearningSettingsRead)
def get_learning_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = interest.get_or_create_model(db, user.id, user.household_id)
    top_items = []
    for k, v in model.weights.items():
        if abs(v) >= 0.05:
            top_items.append((k, round(v, 3)))
    top_items.sort(key=lambda it: abs(it[1]), reverse=True)

    return LearningSettingsRead(
        n_votes=model.n_votes,
        bias=round(model.bias, 3),
        top_interests=top_items[:20],
        muted_terms=model.muted,
    )


@router.post("/learning/mute", response_model=LearningSettingsRead)
def mute_term(
    payload: MuteTermPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = interest.get_or_create_model(db, user.id, user.household_id)
    clean = payload.term.strip().lower()
    muted = list(model.muted)
    if clean and clean not in muted:
        muted.append(clean)
        model.muted = muted
        db.commit()

    return get_learning_settings(user, db)


@router.delete("/learning/mute/{term}", response_model=LearningSettingsRead)
def unmute_term(
    term: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = interest.get_or_create_model(db, user.id, user.household_id)
    clean = term.strip().lower()
    muted = [m for m in model.muted if m != clean]
    model.muted = muted
    db.commit()

    return get_learning_settings(user, db)


@router.post("/learning/reset", response_model=LearningSettingsRead)
def reset_learning_model(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = interest.get_or_create_model(db, user.id, user.household_id)
    model.weights = {}
    model.g2 = {}
    model.bias = 0.0
    model.bias_g2 = 1.0
    model.n_votes = 0
    db.commit()

    return get_learning_settings(user, db)


@router.get("/feed", response_model=FeedSettingsRead)
def get_feed_settings(
    user: User = Depends(get_current_user),
):
    prefs = user.feed_preferences or {}
    return FeedSettingsRead(
        category_order=prefs.get("category_order", []),
        excluded_categories=prefs.get("excluded_categories", []),
        preview_lines=prefs.get("preview_lines", 2),
    )


@router.patch("/feed", response_model=FeedSettingsRead)
def update_feed_settings(
    payload: FeedSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = dict(user.feed_preferences or {})
    if payload.category_order is not None:
        prefs["category_order"] = payload.category_order
    if payload.excluded_categories is not None:
        prefs["excluded_categories"] = payload.excluded_categories
    if payload.preview_lines is not None:
        prefs["preview_lines"] = payload.preview_lines

    user.feed_preferences = prefs
    db.commit()
    return get_feed_settings(user)

