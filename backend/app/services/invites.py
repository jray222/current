"""
Invite-only sign-up.

The instance owner hands out invites for new households; household admins
hand out invites to join their own household. A code is shown once, when it
is created: only its SHA-256 hash is stored. Codes expire, can be revoked,
and are single-use unless created for more uses.

Whether anyone can sign up without an invite is the registration mode:
'invite' (default) or 'open', stored in runtime_config so the instance owner
can switch it without a restart (ALLOW_REGISTRATION is the default).
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Household, Invite, RuntimeConfig

REGISTRATION_MODES = ("invite", "open")
_MODE_KEY = "registration_mode"
# No 0/O or 1/I/L, so a code read aloud or typed from a phone is unambiguous.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def generate_code() -> str:
    """12 random characters (~59 bits), grouped for reading: 'K7QX-M2HD-9TRA'."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode("utf-8")).hexdigest()


def registration_mode(db: Session) -> str:
    row = db.query(RuntimeConfig).filter(RuntimeConfig.key == _MODE_KEY).first()
    if row and row.value in REGISTRATION_MODES:
        return row.value
    return "open" if settings.ALLOW_REGISTRATION else "invite"


_PUBLIC_URL_KEY = "public_url"


def clean_public_url(url: Optional[str]) -> str:
    """'https://dose.example.com/' -> 'https://dose.example.com' ('' if not a web address)."""
    url = (url or "").strip().rstrip("/")
    return url if re.fullmatch(r"https?://[^\s/?#]+(/[^\s?#]*)?", url) else ""


def public_url(db: Session) -> str:
    """Where people reach this Dose from the internet: the owner's setting, else PUBLIC_URL."""
    row = db.query(RuntimeConfig).filter(RuntimeConfig.key == _PUBLIC_URL_KEY).first()
    if row is not None:
        return clean_public_url(row.value)
    return clean_public_url(settings.PUBLIC_URL)


def set_public_url(db: Session, url: Optional[str]) -> str:
    """Saves the owner's public address ('' clears it back to PUBLIC_URL). Raises ValueError if invalid."""
    url = (url or "").strip()
    cleaned = clean_public_url(url)
    if url and not cleaned:
        raise ValueError("Enter a full web address, like https://dose.example.com")
    row = db.query(RuntimeConfig).filter(RuntimeConfig.key == _PUBLIC_URL_KEY).first()
    if not url:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(RuntimeConfig(key=_PUBLIC_URL_KEY, value=cleaned))
    else:
        row.value = cleaned
    db.commit()
    return public_url(db)


def invite_link(db: Session, code: str) -> Optional[str]:
    """The sign-up link for a code, on the public address (None if none is set:
    the app then uses the address it is open on)."""
    base = public_url(db)
    return f"{base}/?invite={code}" if base else None


def set_registration_mode(db: Session, mode: str) -> None:
    row = db.query(RuntimeConfig).filter(RuntimeConfig.key == _MODE_KEY).first()
    if row is None:
        db.add(RuntimeConfig(key=_MODE_KEY, value=mode))
    else:
        row.value = mode
    db.commit()


def invite_state(invite: Invite, now: Optional[datetime] = None) -> str:
    now = _naive_utc(now or _utcnow())
    if invite.revoked_at is not None:
        return "revoked"
    if invite.use_count >= invite.max_uses:
        return "used"
    if _naive_utc(invite.expires_at) <= now:
        return "expired"
    return "active"


def find_valid_invite(db: Session, code: str) -> Optional[Invite]:
    if not normalize_code(code):
        return None
    invite = db.query(Invite).filter(Invite.code_hash == hash_code(code)).first()
    if invite is None or invite_state(invite) != "active":
        return None
    if invite.household_id is not None:
        household = db.get(Household, invite.household_id)
        if household is None:
            return None
    return invite


def create_invite(
    db: Session, created_by_id: int, household_id: Optional[int], note: Optional[str] = None,
    expires_in_days: Optional[int] = None, max_uses: int = 1, grants_admin: bool = False,
) -> tuple[Invite, str]:
    """Creates an invite; returns it with its code (the only time the code exists in plain text)."""
    code = generate_code()
    invite = Invite(
        code_hash=hash_code(code),
        household_id=household_id,
        grants_admin=bool(grants_admin and household_id is not None),
        note=(note or "").strip()[:100] or None,
        created_by_id=created_by_id,
        max_uses=max_uses,
        use_count=0,
        expires_at=_naive_utc(_utcnow() + timedelta(days=expires_in_days or settings.INVITE_DEFAULT_DAYS)),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite, code


def redeem(db: Session, invite: Invite) -> bool:
    """Uses up one use of the invite, atomically: two people racing for the
    last use can't both get in. Part of the caller's transaction."""
    result = db.execute(
        update(Invite)
        .where(Invite.id == invite.id, Invite.revoked_at.is_(None), Invite.use_count < Invite.max_uses)
        .values(use_count=Invite.use_count + 1, last_used_at=_naive_utc(_utcnow()))
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def revoke(db: Session, invite: Invite) -> None:
    if invite.revoked_at is None:
        invite.revoked_at = _naive_utc(_utcnow())
        db.commit()
