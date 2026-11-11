from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.deps import get_current_superuser
from app.models import User
from app.security import verify_password
from app.services import ai as ai_service
from app.services import invites as invite_service
from app.services import keys as key_service

# These settings are instance-wide (the AI key, who may sign up, the server's
# keys), so only the instance owner may read or change them.
router = APIRouter(
    prefix="/api/v1/settings",
    tags=["Settings"],
    dependencies=[Depends(get_current_superuser)],
)


class AISettingsRead(BaseModel):
    anthropic_api_key_set: bool
    # "app" (saved here, encrypted), "environment" (ANTHROPIC_API_KEY) or None.
    key_source: Optional[str] = None
    anthropic_model: str
    suggested_models: list[str]


class AISettingsUpdate(BaseModel):
    # Omit (or send null) to keep a stored key; send "" to clear it.
    anthropic_api_key: Optional[str] = Field(default=None, max_length=400)
    anthropic_model: Optional[str] = Field(default=None, max_length=100)


def _ai(db: Session) -> AISettingsRead:
    effective = ai_service.runtime_settings(db)
    return AISettingsRead(
        anthropic_api_key_set=bool(effective["anthropic_api_key"]),
        key_source=effective["key_source"],
        anthropic_model=effective["anthropic_model"],
        suggested_models=ai_service.SUGGESTED_MODELS,
    )


@router.get("/ai", response_model=AISettingsRead)
def get_ai_settings(db: Session = Depends(get_db)):
    """The AI configuration (database first, then the environment). The key is never returned."""
    return _ai(db)


@router.post("/ai", response_model=AISettingsRead)
def update_ai_settings(payload: AISettingsUpdate, db: Session = Depends(get_db)):
    ai_service.save_settings(db, payload.anthropic_api_key, payload.anthropic_model)
    return _ai(db)


class RegistrationSettings(BaseModel):
    # 'invite': new accounts need an invite link; 'open': anyone can sign up.
    mode: Literal["invite", "open"]
    # Where people reach this Current from the internet; invite links use it.
    public_url: str = ""
    # PUBLIC_URL from the server's environment (used when the owner sets nothing).
    public_url_default: str = ""


class RegistrationSettingsUpdate(BaseModel):
    """Only the fields sent change; public_url "" clears the owner's setting."""
    mode: Optional[Literal["invite", "open"]] = None
    public_url: Optional[str] = Field(default=None, max_length=300)


def _registration(db: Session) -> RegistrationSettings:
    return RegistrationSettings(
        mode=invite_service.registration_mode(db),
        public_url=invite_service.public_url(db),
        public_url_default=invite_service.clean_public_url(app_settings.PUBLIC_URL),
    )


@router.get("/registration", response_model=RegistrationSettings)
def get_registration_settings(db: Session = Depends(get_db)):
    return _registration(db)


@router.post("/registration", response_model=RegistrationSettings)
def update_registration_settings(payload: RegistrationSettingsUpdate, db: Session = Depends(get_db)):
    if payload.mode is not None:
        invite_service.set_registration_mode(db, payload.mode)
    if payload.public_url is not None:
        try:
            invite_service.set_public_url(db, payload.public_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return _registration(db)


# ------------------------------------------------------------ server keys

class KeyActionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _confirm(user: User, payload: KeyActionRequest) -> None:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect.")


def _log(db: Session, request: Request, user: User, event: str) -> None:
    from app.routers.auth import _log_event
    _log_event(db, request, event, user=user)


@router.get("/keys")
def get_keys(db: Session = Depends(get_db)):
    """Where the server's keys live, their fingerprints, and what each one opens.
    Keys themselves are never shown."""
    return key_service.describe(db)


@router.post("/keys/rotate")
def rotate_keys(payload: KeyActionRequest, request: Request, user: User = Depends(get_current_superuser),
                db: Session = Depends(get_db)):
    """Re-encrypts everything with the newest key in DATA_KEYS, then stops trying
    the key made from SECRET_KEY."""
    _confirm(user, payload)
    try:
        result = key_service.rotate(db)
    except key_service.KeyActionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _log(db, request, user, "data_keys_rotated")
    return {**result, "keys": key_service.describe(db)}


@router.post("/keys/accept")
def accept_keys(payload: KeyActionRequest, request: Request, user: User = Depends(get_current_superuser),
                db: Session = Depends(get_db)):
    """After the keys changed: carry on with the current ones."""
    _confirm(user, payload)
    try:
        result = key_service.accept_current(db)
    except key_service.KeyActionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _log(db, request, user, "data_keys_accepted")
    return {**result, "keys": key_service.describe(db)}


@router.post("/keys/sign-out-everyone")
def sign_out_everyone(payload: KeyActionRequest, request: Request, user: User = Depends(get_current_superuser),
                      db: Session = Depends(get_db)):
    """Ends every session on this server, yours too."""
    _confirm(user, payload)
    _log(db, request, user, "signed_everyone_out")
    key_service.sign_everyone_out(db)
    return {"status": "signed_out"}
