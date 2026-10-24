"""
The server's keys: where they are, whether they still open the data, and
moving the data to a new one.

- SECRET_KEY signs sign-ins. Before DATA_KEYS it also made the one key that
  encrypts data, so changing it silently made 2FA secrets and the stored
  Anthropic key unreadable.
- DATA_KEYS (newest first) encrypt that data. Re-encrypting moves every value
  to the newest key in one transaction and then stops trying the key derived
  from SECRET_KEY, so SECRET_KEY can change from then on without losing data.
- The key check: a known value encrypted at first start. If it won't open at
  a later start, the keys changed, and the owner sees that instead of
  "no AI key" and friends.
"""
import json
from datetime import datetime, timezone
from typing import Callable, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.models import RefreshToken, RuntimeConfig, User
from app.security import (
    configured_data_keys, decrypt_secret, encrypt_secret, fingerprint, key_state, legacy_data_key,
    looks_encrypted,
)

CHECK_KEY = "data_key_check"
CHECK_TEXT = "dose key check"
RETIRED_KEY = "legacy_data_key_retired"
SESSIONS_KEY = "sessions_generation"
SIGNED_OUT_KEY = "signed_everyone_out_at"
SEEN_KEY = "key_fingerprints"  # {fingerprint: first day this server ran with it}
ANTHROPIC_KEY = "anthropic_api_key"
# AI provider keys in runtime_config: (key, what it is).
API_KEYS = ((ANTHROPIC_KEY, "Anthropic API key"),)

# Every column holding a value encrypted with the data keys.
_COLUMNS = (
    (User, "totp_secret_encrypted", "2FA secret"),
)

KEY_CHANGED = ("This server's key changed. The stored Anthropic key and 2FA secrets can't be read. "
               "Put the old key back, or reconnect them.")


class KeyActionError(Exception):
    """A key action that can't be done, with a message for the owner."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get(db: Session, key: str) -> Optional[RuntimeConfig]:
    return db.query(RuntimeConfig).filter(RuntimeConfig.key == key).first()


def _set(db: Session, key: str, value: Optional[str]) -> None:
    row = _get(db, key)
    if row is None:
        db.add(RuntimeConfig(key=key, value=value))
    else:
        row.value = value


# ---------------------------------------------------------------- every encrypted value

def _visit(db: Session, fn: Callable[[str, str], Optional[str]]) -> None:
    """Calls fn(ciphertext, what) for every encrypted value; a returned string replaces it."""
    for model, column, what in _COLUMNS:
        for row in db.query(model).filter(getattr(model, column).isnot(None)).all():
            new = fn(getattr(row, column), what)
            if new is not None:
                setattr(row, column, new)
    for key, what in (*API_KEYS, (CHECK_KEY, "key check")):
        row = _get(db, key)
        if row is not None and looks_encrypted(row.value):
            new = fn(row.value, what)
            if new is not None:
                row.value = new


def _opener(value: str) -> Optional[bytes]:
    """The key that opens a value, trying each one (not only the active list)."""
    candidates, _ = configured_data_keys()
    for key in [*candidates, legacy_data_key()]:
        try:
            Fernet(key).decrypt(value.encode("utf-8"))
            return key
        except (InvalidToken, ValueError):
            continue
    return None


def usage(db: Session) -> dict:
    """How many values each key opens, and which values none of them do."""
    counts: dict[bytes, int] = {}
    unreadable: list[str] = []

    def tally(value: str, what: str) -> None:
        key = _opener(value)
        if key is None:
            unreadable.append(what)
        else:
            counts[key] = counts.get(key, 0) + 1

    _visit(db, tally)
    return {"counts": counts, "unreadable": unreadable}


# ---------------------------------------------------------------- startup

def load(db: Session) -> None:
    """At startup: reads what earlier runs decided, encrypts plain AI provider keys,
    and checks the keys still open the data."""
    retired = _get(db, RETIRED_KEY)
    key_state.legacy_retired = bool(retired and retired.value == "1")
    sessions = _get(db, SESSIONS_KEY)
    key_state.sessions_generation = int(sessions.value) if sessions and (sessions.value or "").isdigit() else 0

    for key, what in API_KEYS:
        row = _get(db, key)
        if row is not None and row.value and not looks_encrypted(row.value):
            # Stored in plain text before this version.
            row.value = encrypt_secret(row.value)
            print(f"[startup] Encrypted the stored {what}")

    check = _get(db, CHECK_KEY)
    if check is None or not check.value:
        _set(db, CHECK_KEY, encrypt_secret(CHECK_TEXT))
        key_state.problem = None
    else:
        key_state.problem = None if decrypt_secret(check.value) == CHECK_TEXT else "changed"
    if key_state.problem:
        print(f"[startup] WARNING: {KEY_CHANGED}")

    seen = _seen(db)
    today = _now().date().isoformat()
    for key in [settings.SECRET_KEY, *configured_data_keys()[0]]:
        seen.setdefault(fingerprint(key), today)
    _set(db, SEEN_KEY, json.dumps(seen))
    db.commit()


def _seen(db: Session) -> dict:
    row = _get(db, SEEN_KEY)
    try:
        value = json.loads(row.value) if row and row.value else {}
    except ValueError:
        value = {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- what the owner sees

def describe(db: Session) -> dict:
    seen = _seen(db)
    configured, invalid = configured_data_keys()
    used = usage(db)
    legacy = legacy_data_key()
    file_source = settings.secret_key_source == "file"

    data = [{
        "fingerprint": fingerprint(k), "first_seen": seen.get(fingerprint(k)), "newest": i == 0,
        "values": used["counts"].get(k, 0),
    } for i, k in enumerate(configured)]
    legacy_values = used["counts"].get(legacy, 0)
    total = sum(used["counts"].values())

    advice = []
    if key_state.problem:
        advice.append(KEY_CHANGED)
    if invalid:
        advice.append("DATA_KEYS has an entry that isn't a valid key, so it's ignored. Check for a typo."
                      if invalid == 1 else
                      f"DATA_KEYS has {invalid} entries that aren't valid keys, so they're ignored. Check for typos.")
    if file_source:
        advice.append("The sign-in key is a file in Dose's data volume, next to the database. Copy it into "
                      "SECRET_KEY in Portainer (or docker-compose.yml) so it's a deliberate secret, and keep a "
                      "copy in your password manager.")
    if not configured:
        advice.append("Data is encrypted with a key made from the sign-in key, so changing SECRET_KEY would make "
                      "the Anthropic key and 2FA unreadable. To separate them, make a data key below, "
                      "add it to DATA_KEYS, restart Dose, then re-encrypt.")
    elif legacy_values or (total and data[0]["values"] < total):
        advice.append("Some values still use an older key. Re-encrypt so everything uses the newest one.")
    elif len(configured) > 1 and not any(d["values"] for d in data[1:]):
        advice.append("Nothing uses the older data keys any more. You can remove them from DATA_KEYS.")
    if configured and not key_state.legacy_retired and not legacy_values:
        advice.append("Re-encrypt once to stop trying the key made from SECRET_KEY.")

    signed_out = _get(db, SIGNED_OUT_KEY)
    return {
        "problem": key_state.problem,
        "signing_key": {
            "source": settings.secret_key_source,
            "file": str(settings.secret_key_file) if file_source else None,
            "fingerprint": fingerprint(settings.SECRET_KEY),
            "first_seen": seen.get(fingerprint(settings.SECRET_KEY)),
        },
        "data_keys": data,
        "invalid_data_keys": invalid,
        "legacy": {"retired": key_state.legacy_retired, "values": legacy_values},
        "values": total,
        "unreadable": used["unreadable"],
        "signed_everyone_out_at": signed_out.value if signed_out else None,
        "advice": advice,
    }


def alerts(db: Session) -> list[dict]:
    """For the instance owner, on the dashboard."""
    out = []
    if key_state.problem:
        out.append({
            "key": "keys:changed", "kind": "key_changed", "severity": "danger",
            "title": "This server's key changed", "message": KEY_CHANGED,
            "action": "keys", "dismissible": False,
        })
    _, invalid = configured_data_keys()
    if invalid:
        out.append({
            "key": "keys:invalid", "kind": "key_changed", "severity": "danger",
            "title": "A data key isn't valid",
            "message": "DATA_KEYS has an entry that isn't a valid key, so it's ignored. Check for a typo.",
            "action": "keys", "dismissible": False,
        })
    return out


# ---------------------------------------------------------------- owner actions

def rotate(db: Session) -> dict:
    """Re-encrypts every value with the newest data key, in one transaction, then
    stops trying the key made from SECRET_KEY. Safe to run again."""
    configured, _ = configured_data_keys()
    if not configured:
        raise KeyActionError("Add a data key to DATA_KEYS and restart Dose first.")
    if key_state.problem:
        raise KeyActionError("Fix the key problem first: put the old key back, or use the current keys from now on.")
    skipped: list[str] = []
    moved = 0

    def reencrypt(value: str, what: str) -> Optional[str]:
        nonlocal moved
        plain = decrypt_secret(value)
        if plain is None:
            skipped.append(what)
            return None
        moved += 1
        return encrypt_secret(plain)

    try:
        _visit(db, reencrypt)
        _set(db, RETIRED_KEY, "1")
        db.commit()
    except Exception:
        db.rollback()
        raise
    key_state.legacy_retired = True
    return {"moved": moved, "skipped": skipped, "key": fingerprint(configured[0])}


def accept_current(db: Session) -> dict:
    """After the keys changed: carry on with the current ones. Values the old key
    made stay unreadable (and untouched, in case it turns up)."""
    if not key_state.problem:
        raise KeyActionError("The keys haven't changed.")
    _set(db, CHECK_KEY, encrypt_secret(CHECK_TEXT))
    db.commit()
    key_state.problem = None
    return {"unreadable": usage(db)["unreadable"]}


def sign_everyone_out(db: Session) -> None:
    """Ends every session on this server, the owner's included: what rotating
    the signing key would do, without touching SECRET_KEY. Refresh tokens are
    revoked and access tokens issued before now are refused."""
    generation = key_state.sessions_generation + 1
    db.query(RefreshToken).filter(RefreshToken.revoked == False).update({"revoked": True})  # noqa: E712
    _set(db, SESSIONS_KEY, str(generation))
    _set(db, SIGNED_OUT_KEY, _now().isoformat(timespec="seconds"))
    db.commit()
    key_state.sessions_generation = generation


def reset_state() -> None:
    """Tests: forget what an earlier start learned."""
    key_state.legacy_retired = False
    key_state.problem = None
    key_state.sessions_generation = 0


def stored_secret(value: Optional[str]) -> Optional[str]:
    """A stored AI provider key, readable."""
    if not value:
        return None
    if not looks_encrypted(value):
        return value  # stored before encryption; load() encrypts it at the next start
    return decrypt_secret(value)

