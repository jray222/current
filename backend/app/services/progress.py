"""How well each person knows each card: a small Leitner system.

Box 0 is new. "Knew it" moves a card up a box and pushes its next review out
(1, 3, 7, 16, then 35 days); "Not yet" drops it to box 1 and brings it back in
ten minutes. Sailing past a card only counts it as seen.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Card, CardImage, CardProgress, Deck

INTERVALS = {1: timedelta(days=1), 2: timedelta(days=3), 3: timedelta(days=7), 4: timedelta(days=16),
             5: timedelta(days=35)}
AGAIN = timedelta(minutes=10)
KNOWN_BOX = 3  # a card in box 3 or above counts as known


def _utcnow():
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def record(db: Session, user_id: int, card_id: int, result: str, now: Optional[datetime] = None) -> CardProgress:
    now = now or _utcnow()
    row = db.query(CardProgress).filter(CardProgress.user_id == user_id, CardProgress.card_id == card_id).first()
    if row is None:
        row = CardProgress(user_id=user_id, card_id=card_id, box=0, seen=0, knew=0)
        db.add(row)
    row.seen = (row.seen or 0) + 1
    row.last_seen_at = now
    if result == "knew":
        row.knew = (row.knew or 0) + 1
        row.box = min(5, (row.box or 0) + 1)
        row.due_at = now + INTERVALS[row.box]
    elif result == "again":
        row.box = 1
        row.due_at = now + AGAIN
    elif row.due_at is None:
        # Seen while sailing: due for a first quiz tomorrow.
        row.due_at = now + INTERVALS[1]
    db.commit()
    db.refresh(row)
    return row


def for_user(db: Session, user_id: int, card_ids: list[int]) -> dict[int, CardProgress]:
    if not card_ids:
        return {}
    rows = db.query(CardProgress).filter(CardProgress.user_id == user_id, CardProgress.card_id.in_(card_ids))
    return {r.card_id: r for r in rows}


def summary(rows: dict[int, CardProgress], total: int, now: Optional[datetime] = None) -> dict:
    now = now or _utcnow()
    seen = sum(1 for r in rows.values() if r.seen)
    known = sum(1 for r in rows.values() if (r.box or 0) >= KNOWN_BOX)
    due = sum(1 for r in rows.values() if r.due_at is not None and _aware(r.due_at) <= now)
    return {"total": total, "seen": seen, "known": known, "due": due, "new": total - seen}


def quiz_order(cards: list[Card], rows: dict[int, CardProgress], limit: int, now: Optional[datetime] = None) -> list[int]:
    """Due cards first (most overdue first), then new ones in deck order, then the rest, soonest due first."""
    now = now or _utcnow()
    due, new, later = [], [], []
    for c in cards:
        r = rows.get(c.id)
        if r is None or not r.seen:
            new.append(c)
        elif r.due_at is None or _aware(r.due_at) <= now:
            due.append((_aware(r.due_at) or now, c))
        else:
            later.append((_aware(r.due_at), c))
    ordered = [c for _, c in sorted(due, key=lambda x: x[0])] + new + [c for _, c in sorted(later, key=lambda x: x[0])]
    return [c.id for c in ordered[:limit]]


def deck_of_the_day(db: Session, today: date) -> Optional[Deck]:
    """A different deck each day, cycling through the decks that have pictures, in the order they were added."""
    decks = [d for d in db.query(Deck).order_by(Deck.id).all() if _has_pictures(db, d)]
    if not decks:
        return None
    return decks[today.toordinal() % len(decks)]


def _has_pictures(db: Session, deck: Deck) -> bool:
    return db.query(CardImage.id).join(Card).filter(
        Card.deck_id == deck.id, CardImage.status == "chosen", CardImage.local_path.isnot(None)).first() is not None


def local_today() -> date:
    """Today in the server's time zone (TZ), so the deck of the day turns over at local midnight."""
    from app.config import settings
    if settings.TZ:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(settings.TZ)).date()
        except Exception:
            pass
    return datetime.now().astimezone().date()
