"""
Reset links: setting a new password without email.

A household admin makes a link for a member of their household; the instance
owner makes one for an admin (of any household). Nobody makes one for
themselves, and the instance owner's own password is reset with the server
command (`python -m app.cli reset-password <username>`). A link is shown once
(only a hash of its token is stored), works once, and lasts an hour; making a
new one cancels the old. Using it sets the new password, signs that account
out everywhere and lifts any sign-in pause. Two-step verification stays on,
and backup codes still work.

Reset links are sign-in data, like invites: backups leave them out.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import PasswordResetLink, RefreshToken, User
from app.security import hash_password, validate_password_strength, verify_password
from app.services import invites, lockout

VALID_FOR = timedelta(hours=1)


class ResetError(ValueError):
    """A reset that can't be done, with a message for the person."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()


def why_not(requester: User, target: User) -> Optional[str]:
    """None if requester may make a reset link for target, else why not."""
    if target.id == requester.id:
        return "Change your own password in Account security instead."
    if not target.is_active:
        return "This account is turned off. Turn it back on first."
    if target.is_superuser:
        return "The instance owner's password is reset with the server command reset-password."
    if target.is_admin:
        if not requester.is_superuser:
            return "Only the instance owner can make a reset link for a household admin."
        return None
    if requester.is_admin and requester.household_id == target.household_id:
        return None
    return "Only an admin of this household can make a reset link for it."


def create(db: Session, target: User, created_by_id: Optional[int]) -> tuple[PasswordResetLink, str]:
    """A new link for target (cancelling any older one). Returns it with its token,
    the only time the token exists in plain text."""
    now = _now()
    db.query(PasswordResetLink).filter(
        PasswordResetLink.user_id == target.id, PasswordResetLink.used_at.is_(None),
        PasswordResetLink.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    token = secrets.token_urlsafe(32)
    link = PasswordResetLink(user_id=target.id, token_hash=_hash(token), created_by_id=created_by_id,
                             created_at=now, expires_at=now + VALID_FOR)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link, token


def url(db: Session, token: str) -> Optional[str]:
    """The link on the public address (None if none is set: the app adds the address it's open on)."""
    base = invites.public_url(db)
    return f"{base}/?reset={token}" if base else None


def find(db: Session, token: str) -> Optional[PasswordResetLink]:
    """The link if it can still be used."""
    if not token or len(token) > 200:
        return None
    link = db.query(PasswordResetLink).filter(PasswordResetLink.token_hash == _hash(token)).first()
    if link is None or link.used_at is not None or link.revoked_at is not None or link.expires_at <= _now():
        return None
    user = db.get(User, link.user_id)
    if user is None or not user.is_active:
        return None
    return link


def set_password(db: Session, user: User, new_password: str) -> None:
    """New password, signed out everywhere, sign-in pause lifted. Part of the caller's transaction."""
    error = validate_password_strength(new_password)
    if error:
        raise ResetError(error)
    if verify_password(new_password, user.password_hash):
        raise ResetError("Choose a password different from the old one.")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    lockout.clear(db, user)


def use(db: Session, token: str, new_password: str) -> User:
    """Sets the new password with a link, using it up. Raises ResetError."""
    link = find(db, token)
    if link is None:
        raise ResetError("This reset link is invalid, used or expired. Ask for a new one.")
    user = db.get(User, link.user_id)
    error = validate_password_strength(new_password)
    if error:
        raise ResetError(error)
    # Used up atomically: two tabs racing with the same link can't both set a password.
    taken = db.execute(
        update(PasswordResetLink)
        .where(PasswordResetLink.id == link.id, PasswordResetLink.used_at.is_(None),
               PasswordResetLink.revoked_at.is_(None))
        .values(used_at=_now())
        .execution_options(synchronize_session=False)
    )
    if taken.rowcount != 1:
        db.rollback()
        raise ResetError("This reset link is invalid, used or expired. Ask for a new one.")
    try:
        set_password(db, user, new_password)
    except ResetError:
        db.rollback()
        raise
    db.commit()
    return user


def delete_for(db: Session, user_ids) -> None:
    """Before deleting sign-ins."""
    ids = list(user_ids)
    if ids:
        db.query(PasswordResetLink).filter(PasswordResetLink.user_id.in_(ids)).delete(synchronize_session=False)
