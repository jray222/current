from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)

    # Password is never stored in plaintext - only a salted bcrypt hash.
    password_hash = Column(String(255), nullable=False)
    password_changed_at = Column(DateTime, default=_utcnow)

    household_id = Column(Integer, ForeignKey("households.id"), nullable=False, index=True)

    is_active = Column(Boolean, default=True, nullable=False)
    # Household administrator: can add/deactivate members of their household.
    is_admin = Column(Boolean, default=False, nullable=False)
    # Instance owner (the very first account): manages instance-wide settings
    # such as the AI key. Never granted to self-registered or invited users.
    is_superuser = Column(Boolean, default=False, nullable=False)
    # The invite this account signed up with, if any (plain id, see Invite).
    invite_id = Column(Integer, nullable=True)

    # --- Two-Factor Authentication (TOTP, RFC 6238) ---
    # Encrypted at rest using a Fernet key from DATA_KEYS or SECRET_KEY.
    # `totp_enabled` only flips to True once the user has confirmed a code,
    # preventing accidental lockout from an unconfirmed secret.
    totp_secret_encrypted = Column(String(255), nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    totp_confirmed_at = Column(DateTime, nullable=True)
    # Last accepted TOTP time-step; codes at or before it are rejected so an
    # intercepted code can't be replayed within its validity window.
    totp_last_used_step = Column(Integer, nullable=True)

    # --- Brute-force protection (services/lockout.py) ---
    # Wrong passwords from browsers that have never signed in to this account,
    # counted within 15 minutes; enough of them pause sign-in from such
    # browsers until locked_until. Known devices aren't affected.
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    last_failed_at = Column(DateTime, nullable=True)
    locked_until = Column(DateTime, nullable=True)
    # Pauses so far in a row; each one lasts twice as long, up to a day.
    lockout_level = Column(Integer, default=0, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    household = relationship("Household", back_populates="users")
    backup_codes = relationship("BackupCode", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class BackupCode(Base):
    """One-time-use recovery codes issued when 2FA is enabled."""
    __tablename__ = "backup_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="backup_codes")


class RefreshToken(Base):
    """
    Server-side record of issued refresh tokens (hashed, never stored in
    plaintext) to allow revocation, rotation-reuse detection, and
    'logout everywhere'.
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    replaced_by_hash = Column(String(128), nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class PasswordResetLink(Base):
    """
    A one-time link that sets a new password (services/password_resets.py),
    made by a household admin for a member, or by the instance owner for an
    admin. Only the token's SHA-256 hash is stored, so the link is shown once.
    Valid for an hour and for one use; making a new one cancels the old.
    """
    __tablename__ = "password_reset_links"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    # Plain id (no FK), like invites: who made it.
    created_by_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class LoginAuditLog(Base):
    """Append-only audit trail of authentication events for security review."""
    __tablename__ = "login_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    username_attempted = Column(String(64), nullable=True)
    event = Column(String(40), nullable=False)  # login_success, login_failed, lockout, 2fa_success, 2fa_failed, logout, ...
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
