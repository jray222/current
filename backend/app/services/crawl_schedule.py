"""Automatic scheduled crawling on each household's timetable with nightly retention pruning.
"""
from datetime import date, datetime, time, timedelta, timezone, tzinfo
import logging
import os
from pathlib import Path
import threading
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.household import Household
from app.services import crawler
from app.services import prune

logger = logging.getLogger("current.scheduler")

EVERY_HOURS = (1, 2, 4, 6, 8, 12, 24)
DEFAULT_START_TIME = "06:00"
DEFAULT_EVERY_HOURS = 24
CHECK_EVERY_SECONDS = 60
DAY_MINUTES = 24 * 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def zone() -> tzinfo:
    """Returns local time zone or UTC."""
    configured = (settings.TZ or "").strip().lstrip(":")
    for name in (configured, "UTC"):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return timezone.utc


def parse_time_to_minutes(time_str: str) -> int:
    """Parses 'HH:MM' string to minutes past midnight."""
    try:
        parts = time_str.strip().split(":")
        h = int(parts[0]) % 24
        m = int(parts[1]) % 60
        return h * 60 + m
    except Exception:
        return 6 * 60  # Default 06:00


def times_of_day(start_minute: int, every_hours: int) -> list[int]:
    """Minutes after midnight for each run time during a 24-hour cycle."""
    if every_hours not in EVERY_HOURS:
        every_hours = DEFAULT_EVERY_HOURS
    step = every_hours * 60
    count = max(1, 24 // every_hours)
    return sorted({(start_minute + k * step) % DAY_MINUTES for k in range(count)})


def _moments(around: date, start_minute: int, every_hours: int, tz: tzinfo) -> list[datetime]:
    out = set()
    for offset in range(-2, 2):
        day = around + timedelta(days=offset)
        for minute in times_of_day(start_minute, every_hours):
            local = datetime.combine(day, time(minute // 60, minute % 60), tzinfo=tz)
            out.add(_naive_utc(local))
    return sorted(out)


def latest_time(now: datetime, start_minute: int, every_hours: int, tz: tzinfo) -> datetime:
    moments = _moments(now.date(), start_minute, every_hours, tz)
    past = [m for m in moments if m <= now]
    return past[-1] if past else now


def next_time(now: datetime, start_minute: int, every_hours: int, tz: tzinfo) -> datetime:
    moments = _moments(now.date(), start_minute, every_hours, tz)
    future = [m for m in moments if m > now]
    return future[0] if future else now + timedelta(hours=every_hours)


def should_crawl_household(household: Household, now: Optional[datetime] = None) -> bool:
    """Returns True if the household is due for a scheduled crawl."""
    if not household.crawl_enabled:
        return False

    now = _naive_utc(now or _utcnow())
    tz = zone()
    start_minute = parse_time_to_minutes(household.crawl_time or DEFAULT_START_TIME)
    every_hours = household.crawl_every_hours if household.crawl_every_hours in EVERY_HOURS else DEFAULT_EVERY_HOURS

    handled = household.crawl_handled_at
    if handled is None:
        return True

    moment = latest_time(now, start_minute, every_hours, tz)
    return moment > handled


def due(db: Session, now: Optional[datetime] = None) -> list[int]:
    """Returns IDs of households that are due for scheduled crawl and marks them handled."""
    now = _naive_utc(now or _utcnow())
    due_ids = []
    households = db.query(Household).filter(Household.crawl_enabled == 1).all()

    for h in households:
        if should_crawl_household(h, now):
            h.crawl_handled_at = now
            due_ids.append(h.id)

    if due_ids:
        db.commit()
    return due_ids


class CrawlScheduler:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_prune_date: Optional[date] = None

    def start(self) -> None:
        if self._thread is not None or not settings.SCHEDULER_ENABLED:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="current-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_due(self, now: Optional[datetime] = None) -> list[int]:
        with SessionLocal() as db:
            household_ids = due(db, now)

        for hid in household_ids:
            try:
                crawler.crawl_household(hid, trigger="schedule")
            except Exception as e:
                logger.error(f"Error triggering scheduled crawl for household {hid}: {e}")

        # Nightly maintenance check (run prune once per day)
        check_now = now or _utcnow()
        if self._last_prune_date != check_now.date():
            with SessionLocal() as db:
                try:
                    prune.prune_retention(db)
                    self._last_prune_date = check_now.date()
                except Exception as e:
                    logger.error(f"Nightly retention prune failed: {e}")

        return household_ids

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_EVERY_SECONDS):
            try:
                self.run_due()
            except Exception:
                logger.exception("Scheduled crawl loop error")


crawl_scheduler = CrawlScheduler()
