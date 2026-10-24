"""
Sign-in lockout with known-device cookies (the OWASP "device cookie" pattern).

A browser that signs in to an account keeps a signed cookie for that account
(one per account, so two people can share a computer). Then:

- Wrong passwords from browsers without one count against the username: 5
  within 15 minutes pause sign-in from unknown browsers for 15 minutes, twice
  as long each time it happens again, up to a day.
- A known browser counts its own wrong passwords and is paused on its own, so
  someone guessing a password can't lock the owner out of their own phone.
- Every refusal looks the same: the same message and status, and a password
  hash is always checked, so nothing tells a locked account from a wrong
  password or an unknown name.

Known-browser counts are kept in memory (Dose is one process), so a restart
forgets them; the per-username count is on the user row.
"""
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LoginAuditLog, User
from app.security import create_device_token, decode_token

DEVICE_COOKIE_PREFIX = "dose_device_"
DEVICE_DAYS = 365
WINDOW = timedelta(minutes=15)  # wrong passwords further apart than this start a new count
MAX_PAUSE = timedelta(hours=24)
# A pause that ended this long ago, with no wrong password since, no longer doubles the next one.
LEVEL_FORGOTTEN_AFTER = timedelta(hours=24)

# Audit events that are someone failing to sign in to an account.
FAILURE_EVENTS = ("login_failed_bad_password", "login_blocked_locked", "2fa_failed", "2fa_blocked_locked")
SUCCESS_EVENTS = ("login_success", "2fa_success", "register", "register_with_invite")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- counting

@dataclass
class _DeviceRecord:
    """The same fields the user row has, for one known browser."""
    failed_login_attempts: int = 0
    last_failed_at: Optional[datetime] = None
    locked_until: Optional[datetime] = None
    lockout_level: int = 0


_devices: dict[tuple[int, str], _DeviceRecord] = {}
_devices_lock = threading.Lock()


def reset() -> None:
    """Forgets every known browser's count (tests)."""
    with _devices_lock:
        _devices.clear()


def _paused(record, now: datetime) -> bool:
    until = _utc(record.locked_until)
    return bool(until and until > now)


def _count_failure(record, now: datetime) -> bool:
    """Adds a wrong password; True when it starts a pause."""
    last = _utc(record.last_failed_at)
    if last is None or now - last > WINDOW:
        record.failed_login_attempts = 0
    last_seen = max((t for t in (last, _utc(record.locked_until)) if t), default=None)
    if last_seen is None or now - last_seen > LEVEL_FORGOTTEN_AFTER:
        record.lockout_level = 0
    record.failed_login_attempts = (record.failed_login_attempts or 0) + 1
    record.last_failed_at = now
    if record.failed_login_attempts < settings.MAX_FAILED_LOGIN_ATTEMPTS:
        return False
    pause = timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES) * (2 ** min(record.lockout_level or 0, 10))
    record.locked_until = now + min(pause, MAX_PAUSE)
    record.lockout_level = (record.lockout_level or 0) + 1
    record.failed_login_attempts = 0
    return True


def _clear(record) -> None:
    record.failed_login_attempts = 0
    record.last_failed_at = None
    record.locked_until = None
    record.lockout_level = 0


def _device_record(user: User, device: str) -> _DeviceRecord:
    return _devices.setdefault((user.id, device), _DeviceRecord())


def is_locked(user: User, device: Optional[str]) -> bool:
    """Whether sign-in to this account from this browser is paused."""
    now = _now()
    if device:
        with _devices_lock:
            record = _devices.get((user.id, device))
            return bool(record and _paused(record, now))
    return _paused(user, now)


def register_failure(db: Session, user: User, device: Optional[str]) -> bool:
    """Counts a wrong password or code; True when it starts a pause."""
    now = _now()
    if device:
        with _devices_lock:
            return _count_failure(_device_record(user, device), now)
    started = _count_failure(user, now)
    db.commit()
    return started


def register_success(db: Session, user: User, device: Optional[str]) -> None:
    """A sign-in from a known browser clears only that browser's count: the
    owner signing in on their phone mustn't hand a guesser a fresh 5 tries. One
    from an unknown browser (possible only when unknown browsers aren't
    paused) clears the account's count."""
    if device:
        with _devices_lock:
            _devices.pop((user.id, device), None)
        return
    _clear(user)
    db.commit()


def clear(db: Session, user: User) -> None:
    """The owner's or an admin's "Clear the lock": every pause on this account."""
    _clear(user)
    with _devices_lock:
        for key in [k for k in _devices if k[0] == user.id]:
            del _devices[key]
    db.commit()


def locked_until(user: User) -> Optional[datetime]:
    """When the pause on unknown browsers ends, if one is on."""
    until = _utc(user.locked_until)
    return until if until and until > _now() else None


# ---------------------------------------------------------------- the cookie

def cookie_name(user_id: int) -> str:
    return f"{DEVICE_COOKIE_PREFIX}{user_id}"


def known_device(request: Request, user: User) -> Optional[str]:
    """This browser's id for the account, if it has signed in to it before."""
    token = request.cookies.get(cookie_name(user.id))
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "device" or payload.get("sub") != str(user.id):
        return None
    nonce = payload.get("nonce")
    return nonce if isinstance(nonce, str) and nonce else None


def remember_device(response: Response, user: User, device: Optional[str] = None) -> None:
    """Sets (or renews) the known-device cookie after a successful sign-in."""
    response.set_cookie(
        key=cookie_name(user.id),
        value=create_device_token(user.id, device or secrets.token_hex(16), DEVICE_DAYS),
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        max_age=DEVICE_DAYS * 86400,
        path="/api/v1/auth",
    )


# ---------------------------------------------------------------- telling people

def failures_since_last_visit(db: Session, user: User) -> Optional[dict]:
    """Failed sign-ins to this account since its last sign-in, for the notice
    shown on the next one: {"count", "addresses", "last_at"}."""
    since = _utc(user.last_login_at) or _utc(user.created_at)
    query = db.query(LoginAuditLog).filter(LoginAuditLog.user_id == user.id,
                                           LoginAuditLog.event.in_(FAILURE_EVENTS))
    if since:
        query = query.filter(LoginAuditLog.created_at > since.replace(tzinfo=None))
    rows = query.all()
    if not rows:
        return None
    return {
        "count": len(rows),
        "addresses": len({r.ip_address for r in rows if r.ip_address}) or 1,
        "last_at": max(_utc(r.created_at) for r in rows),
    }
