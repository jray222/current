"""
Core security primitives for authentication:
  - Password hashing & verification (bcrypt)
  - Password strength policy enforcement
  - JWT access token + stateless MFA-challenge token creation/verification
  - Opaque, hashed refresh tokens
  - Known-device cookies for the sign-in lockout (services/lockout.py)
  - Encryption at rest (Fernet): DATA_KEYS, else a key derived from SECRET_KEY
  - One-time backup (recovery) code generation & hashing

Keeping all of this in one module makes it easy to audit the entirety of
the app's cryptographic surface area in one place.
"""
import base64
import hashlib
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings

# --------------------------------------------------------------------------
# Password hashing (bcrypt, salted, adaptive cost factor)
# --------------------------------------------------------------------------

BCRYPT_ROUNDS = 12
MAX_PASSWORD_BYTES = 72  # bcrypt hard limit

# A small deny-list of extremely common passwords, checked in addition to
# the structural policy below. Not exhaustive - just a cheap extra guard.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789",
    "qwerty123", "letmein1", "admin1234", "welcome1", "iloveyou1",
}

PASSWORD_POLICY_DESCRIPTION = (
    "Password must be 12-72 characters and include at least one uppercase "
    "letter, one lowercase letter, one number, and one special character."
)


def validate_password_strength(password: str) -> Optional[str]:
    """Return an error message if the password is too weak, else None."""
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Password must not exceed {MAX_PASSWORD_BYTES} bytes."
    if len(password) < 12:
        return "Password must be at least 12 characters long."
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one number."
    if not re.search(r"[^\w\s]", password):
        return "Password must contain at least one special character."
    if password.lower() in _COMMON_PASSWORDS:
        return "This password is too common. Please choose a stronger password."
    return None


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# JWT access tokens & short-lived MFA challenge tokens
# --------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, extra_claims: Optional[dict] = None) -> str:
    now = _now()
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        # iat to the microsecond: a password change refuses tokens from before
        # it even within the same second (iat itself is whole seconds).
        "t": now.timestamp(),
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(16),
        "gen": key_state.sessions_generation,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_mfa_challenge_token(user_id: int) -> str:
    """Short-lived token proving the user passed step 1 (password) of login,
    used only to complete step 2 (TOTP/backup code) — cannot be used to
    access any protected resource."""
    payload = {
        "sub": str(user_id),
        "type": "mfa_pending",
        "iat": _now(),
        "exp": _now() + timedelta(minutes=settings.MFA_CHALLENGE_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# --------------------------------------------------------------------------
# Opaque refresh tokens (random string, only the SHA-256 hash is persisted)
# --------------------------------------------------------------------------

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Encryption at rest: 2FA secrets and the stored Anthropic key (services/keys.py lists them all).
# --------------------------------------------------------------------------

class KeyState:
    """What the server learned about its keys at startup (services/keys.py)."""
    # Every value was re-encrypted with DATA_KEYS, so the key derived from
    # SECRET_KEY no longer opens anything and isn't tried.
    legacy_retired: bool = False
    # "changed" when the stored key check won't open: the keys aren't the ones
    # the data was encrypted with.
    problem: Optional[str] = None
    # Bumped by "Sign everyone out": access tokens carry the number they were
    # issued under, and older ones are refused.
    sessions_generation: int = 0


key_state = KeyState()


def legacy_data_key() -> bytes:
    """The key every install used before DATA_KEYS: derived from SECRET_KEY."""
    key_material = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_material)


def configured_data_keys() -> tuple[list[bytes], int]:
    """DATA_KEYS, newest first, and how many entries aren't valid keys (skipped)."""
    keys, invalid = [], 0
    for raw in settings.DATA_KEYS.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            Fernet(raw.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            invalid += 1
            continue
        keys.append(raw.encode("ascii"))
    return keys, invalid


def data_keys() -> list[bytes]:
    """Every key that may open a value, newest (the one that encrypts) first."""
    keys, _ = configured_data_keys()
    if not keys or not key_state.legacy_retired:
        keys.append(legacy_data_key())
    return keys


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in data_keys()])


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> Optional[str]:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def looks_encrypted(value: Optional[str]) -> bool:
    """Fernet tokens start with this (version byte, then a timestamp)."""
    return bool(value) and value.startswith("gAAAAA")


def fingerprint(key: bytes | str) -> str:
    """A short name for a key that reveals nothing about it, e.g. 3f9a-07c2-b1d4."""
    raw = key.encode("utf-8") if isinstance(key, str) else key
    digest = hashlib.sha256(b"current key fingerprint\0" + raw).hexdigest()[:12]
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:]}"


# --------------------------------------------------------------------------
# Known-device cookies (services/lockout.py)
# --------------------------------------------------------------------------

def create_device_token(user_id: int, nonce: str, days: int) -> str:
    payload = {
        "sub": str(user_id),
        "type": "device",
        "nonce": nonce,
        "iat": _now(),
        "exp": _now() + timedelta(days=days),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# --------------------------------------------------------------------------
# Backup / recovery codes
# --------------------------------------------------------------------------

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_backup_codes(count: int = 10) -> list[str]:
    """Generate human-friendly one-time codes, e.g. 'X7F3-9KLM'."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_backup_code(code: str) -> str:
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
