"""Where the Anthropic key and model come from: the owner's stored settings
(Settings -> AI, key encrypted) first, else ANTHROPIC_API_KEY / ANTHROPIC_MODEL
from the environment. Nothing in Current needs a key; callers fall back when
there isn't one."""
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import RuntimeConfig
from app.services import keys as key_service

MODEL_KEY = "anthropic_model"
# Offered in the settings screen; any other name can be typed.
SUGGESTED_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]


def _get(db: Session, key: str) -> Optional[RuntimeConfig]:
    return db.query(RuntimeConfig).filter(RuntimeConfig.key == key).first()


def runtime_settings(db: Session) -> dict:
    """The effective key (readable), where it came from, and the model."""
    stored = _get(db, key_service.ANTHROPIC_KEY)
    stored_key = key_service.stored_secret(stored.value) if stored and stored.value else None
    env_key = (settings.ANTHROPIC_API_KEY or "").strip() or None
    model_row = _get(db, MODEL_KEY)
    model = (model_row.value or "").strip() if model_row and model_row.value else ""
    return {
        "anthropic_api_key": stored_key or env_key,
        "key_source": "app" if stored_key else ("environment" if env_key else None),
        "anthropic_model": model or settings.ANTHROPIC_MODEL,
    }


def save_settings(db: Session, api_key: Optional[str], model: Optional[str]) -> None:
    """api_key None keeps the stored key, "" clears it. model None keeps it, "" goes back to the default."""
    from app.security import encrypt_secret

    if api_key is not None:
        api_key = api_key.strip()
        row = _get(db, key_service.ANTHROPIC_KEY)
        if row is None:
            db.add(RuntimeConfig(key=key_service.ANTHROPIC_KEY, value=encrypt_secret(api_key) if api_key else ""))
        else:
            row.value = encrypt_secret(api_key) if api_key else ""
    if model is not None:
        model = model.strip()
        row = _get(db, MODEL_KEY)
        if row is None:
            db.add(RuntimeConfig(key=MODEL_KEY, value=model))
        else:
            row.value = model
    db.commit()
