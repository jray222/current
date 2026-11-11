import base64
import hmac
import io
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin_user, get_current_superuser, get_current_user, get_client_ip
from app.config import settings
from app.models import BackupCode, Household, Invite, LoginAuditLog, RefreshToken, User
from app.services import invites as invite_service
from app.services import lockout, password_resets
from app.services.households import create_household
from app.rate_limit import enforce_auth_rate_limit
from app.schemas_auth import (
    BackupCodesRegenerateRequest,
    BootstrapStatus,
    ChangePasswordRequest,
    CreateUserRequest,
    InviteCheck,
    InviteCreate,
    InviteCreated,
    InviteRead,
    LoginRequest,
    MFARequiredResponse,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
    TwoFactorConfirmRequest,
    TwoFactorConfirmResponse,
    TwoFactorDisableRequest,
    TwoFactorSetupResponse,
    FailedAttempts,
    OtherAdmin,
    ResetCheck,
    ResetLinkCreated,
    ResetRequest,
    UserPublic,
    VerifyMFARequest,
)
from app.security import (
    create_access_token,
    create_mfa_challenge_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    generate_backup_codes,
    generate_refresh_token,
    hash_backup_code,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# A hash of a random, never-used password, used purely to burn CPU time on
# "user not found" paths so login timing doesn't reveal valid usernames.
_DUMMY_HASH = hash_password("never-matches-anything-Zz9!")

# Every refused sign-in gets this, whatever the reason (unknown name, wrong
# password, paused account, deactivated user), with the same status.
GENERIC_LOGIN_ERROR = "Invalid username or password."
GENERIC_CODE_ERROR = "Invalid authentication code."


def _now():
    return datetime.now(timezone.utc)


def _log_event(db: Session, request: Request, event: str, user: User | None = None, username_attempted: str | None = None):
    entry = LoginAuditLog(
        user_id=user.id if user else None,
        username_attempted=username_attempted or (user.username if user else None),
        event=event,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:255],
    )
    db.add(entry)
    db.commit()


def _user_count(db: Session) -> int:
    return db.query(User).count()


def _register_successful_login(db: Session, user: User, request: Request):
    user.last_login_at = _now()
    user.last_login_ip = get_client_ip(request)
    db.commit()


def _finish_sign_in(db: Session, user: User, request: Request, response: Response, device: str | None,
                    event: str) -> TokenResponse:
    """Password (and code) accepted: clears the counts, remembers this browser,
    and tells the person about failed attempts since their last visit."""
    failed = lockout.failures_since_last_visit(db, user)
    lockout.register_success(db, user, device)
    _register_successful_login(db, user, request)
    _log_event(db, request, event, user=user)
    lockout.remember_device(response, user, device)
    tokens = _issue_token_pair(db, user, request, response)
    tokens.failed_attempts = FailedAttempts(**failed) if failed else None
    return tokens


def _issue_token_pair(db: Session, user: User, request: Request, response: Response) -> TokenResponse:
    access_token = create_access_token(user.id)

    raw_refresh = generate_refresh_token()
    refresh_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("user-agent", "")[:255],
        ip_address=get_client_ip(request),
    )
    db.add(refresh_row)
    db.commit()

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublic.from_user(user),
    )


def _verify_totp(db: Session, user: User, code: str) -> bool:
    """
    Checks a TOTP code (allowing +/-1 step of clock drift) and records the
    accepted time-step, so the same code can't be replayed while still valid.
    """
    secret = decrypt_secret(user.totp_secret_encrypted) if user.totp_secret_encrypted else None
    code = code.replace(" ", "")
    if not secret or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    current_step = totp.timecode(datetime.now(timezone.utc))
    for step in (current_step - 1, current_step, current_step + 1):
        if user.totp_last_used_step is not None and step <= user.totp_last_used_step:
            continue
        if hmac.compare_digest(totp.generate_otp(step), code):
            user.totp_last_used_step = step
            db.commit()
            return True
    return False


def _verify_totp_or_backup_code(db: Session, user: User, code: str) -> bool:
    code = (code or "").strip()
    if not code:
        return False

    if user.totp_secret_encrypted and _verify_totp(db, user, code):
        return True

    # Fall back to backup/recovery codes (one-time use)
    code_hash = hash_backup_code(code)
    backup = (
        db.query(BackupCode)
        .filter(BackupCode.user_id == user.id, BackupCode.code_hash == code_hash, BackupCode.used == False)  # noqa: E712
        .first()
    )
    if backup:
        backup.used = True
        backup.used_at = _now()
        db.commit()
        return True

    return False


def confirm_identity(db: Session, user: User, password: str, code: str | None) -> None:
    """Your password again, and a two-step code (or a backup code) if it's on,
    before something that can't be taken back (export, delete, leave)."""
    if not verify_password(password or "", user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect.")
    if user.totp_enabled:
        if not (code or "").strip():
            raise HTTPException(status_code=400, detail="Enter the code from your authenticator app (or a backup code).")
        if not _verify_totp_or_backup_code(db, user, code):
            raise HTTPException(status_code=400, detail=GENERIC_CODE_ERROR)


# --------------------------------------------------------------------------
# Public endpoints
# --------------------------------------------------------------------------

@router.get("/bootstrap-status", response_model=BootstrapStatus)
def bootstrap_status(db: Session = Depends(get_db)):
    setup_required = _user_count(db) == 0
    is_open = invite_service.registration_mode(db) == "open"
    return BootstrapStatus(
        setup_required=setup_required,
        registration_open=setup_required or is_open,
        invite_only=not setup_required and not is_open,
    )


INVALID_INVITE = "This invite is invalid, used up or expired. Ask for a new one."


@router.post("/register", response_model=TokenResponse, dependencies=[Depends(enforce_auth_rate_limit)])
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Signs up a new user. The very first account becomes the instance owner.
    After that, an invite code is required unless registration is open: an
    invite from the instance owner creates a new household with the user as
    its admin; an invite from a household admin joins that household. Open
    registration (no code) creates a new household.
    """
    is_first_user = _user_count(db) == 0
    invite = None
    if not is_first_user:
        if payload.invite_code and payload.invite_code.strip():
            invite = invite_service.find_valid_invite(db, payload.invite_code)
            if invite is None:
                _log_event(db, request, "register_bad_invite", username_attempted=payload.username)
                raise HTTPException(status_code=400, detail=INVALID_INVITE)
        elif invite_service.registration_mode(db) != "open":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sign-up is by invitation only. Ask whoever runs this Current for an invite link.",
            )

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")

    error = validate_password_strength(payload.password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already in use.")

    # Uses up the invite in the same transaction as the new account.
    if invite is not None and not invite_service.redeem(db, invite):
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_INVITE)

    if invite is not None and invite.household_id is not None:
        household_id, is_admin = invite.household_id, invite.grants_admin
    else:
        household = create_household(db, payload.household_name or f"{payload.username}'s Household")
        household_id, is_admin = household.id, True
    user = User(
        household_id=household_id,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=is_admin,
        is_superuser=is_first_user,
        is_active=True,
        invite_id=invite.id if invite is not None else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _log_event(db, request, "register_with_invite" if invite is not None else "register", user=user)
    lockout.remember_device(response, user)
    return _issue_token_pair(db, user, request, response)


@router.get("/invites/check", response_model=InviteCheck, dependencies=[Depends(enforce_auth_rate_limit)])
def check_invite(code: str = Query(..., max_length=64), db: Session = Depends(get_db)):
    """Lets the sign-up page show what an invite link is for before the form is filled in."""
    invite = invite_service.find_valid_invite(db, code)
    if invite is None:
        return InviteCheck(valid=False)
    household = db.get(Household, invite.household_id) if invite.household_id else None
    return InviteCheck(
        valid=True,
        kind="member" if household else "household",
        household_name=household.name if household else None,
        expires_at=invite.expires_at,
    )


@router.post("/login", dependencies=[Depends(enforce_auth_rate_limit)])
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Step 1 of signing in. Refusals all look alike (see services/lockout.py):
    the same answer, and always one password check, so neither the message nor
    the time taken says whether the name exists or the account is paused."""
    user = db.query(User).filter(User.username == payload.username).first()

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        _log_event(db, request, "login_failed_unknown_user", username_attempted=payload.username)
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    device = lockout.known_device(request, user)
    password_ok = verify_password(payload.password, user.password_hash)

    if lockout.is_locked(user, device):
        # Paused, even for the right password: otherwise the pause would only slow a guesser down.
        _log_event(db, request, "login_blocked_locked", user=user)
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    if not user.is_active:
        _log_event(db, request, "login_failed_inactive", user=user)
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    if not password_ok:
        paused = lockout.register_failure(db, user, device)
        _log_event(db, request, "login_failed_bad_password", user=user)
        if paused:
            _log_event(db, request, "lockout_device" if device else "lockout", user=user)
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    if user.totp_enabled:
        _log_event(db, request, "login_password_ok_awaiting_2fa", user=user)
        return MFARequiredResponse(mfa_token=create_mfa_challenge_token(user.id))

    return _finish_sign_in(db, user, request, response, device, "login_success")


@router.post("/login/verify-2fa", response_model=TokenResponse, dependencies=[Depends(enforce_auth_rate_limit)])
def verify_2fa(payload: VerifyMFARequest, request: Request, response: Response, db: Session = Depends(get_db)):
    token_payload = decode_token(payload.mfa_token)
    if not token_payload or token_payload.get("type") != "mfa_pending":
        raise HTTPException(status_code=401, detail="MFA session expired or invalid. Please log in again.")

    try:
        user_id = int(token_payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="MFA session expired or invalid. Please log in again.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active or not user.totp_enabled:
        raise HTTPException(status_code=401, detail="MFA session expired or invalid. Please log in again.")

    # Wrong codes count like wrong passwords. A paused account gets the same
    # answer as a wrong code, and the code isn't checked (a backup code would be used up).
    device = lockout.known_device(request, user)
    if lockout.is_locked(user, device):
        _log_event(db, request, "2fa_blocked_locked", user=user)
        raise HTTPException(status_code=401, detail=GENERIC_CODE_ERROR)

    if not _verify_totp_or_backup_code(db, user, payload.code):
        paused = lockout.register_failure(db, user, device)
        _log_event(db, request, "2fa_failed", user=user)
        if paused:
            _log_event(db, request, "lockout_device" if device else "lockout", user=user)
        raise HTTPException(status_code=401, detail=GENERIC_CODE_ERROR)

    return _finish_sign_in(db, user, request, response, device, "2fa_success")


@router.post("/refresh", response_model=RefreshResponse)
def refresh_access_token(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="No refresh session found. Please log in.")

    token_hash = hash_refresh_token(raw_token)
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not row or row.revoked or row.expires_at.replace(tzinfo=timezone.utc) < _now():
        # If a revoked-but-known token is replayed, treat it as a possible
        # theft and revoke the entire session family for that user.
        if row and row.revoked:
            db.query(RefreshToken).filter(RefreshToken.user_id == row.user_id).update({"revoked": True})
            db.commit()
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    # Rotate: revoke the old refresh token and issue a brand new one.
    row.revoked = True
    new_raw = generate_refresh_token()
    row.replaced_by_hash = hash_refresh_token(new_raw)
    new_row = RefreshToken(
        user_id=user.id,
        token_hash=row.replaced_by_hash,
        expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("user-agent", "")[:255],
        ip_address=get_client_ip(request),
    )
    db.add(new_row)
    db.commit()

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=new_raw,
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    access_token = create_access_token(user.id)
    return RefreshResponse(access_token=access_token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if row:
            row.revoked = True
            db.commit()
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return {"status": "logged_out"}


@router.get("/reset/check", response_model=ResetCheck, dependencies=[Depends(enforce_auth_rate_limit)])
def check_reset_link(token: str = Query(..., max_length=200), db: Session = Depends(get_db)):
    """Lets the reset page say whose password it sets before the form is filled in."""
    link = password_resets.find(db, token)
    if link is None:
        return ResetCheck(valid=False)
    return ResetCheck(valid=True, username=db.get(User, link.user_id).username, expires_at=link.expires_at)


@router.post("/reset", dependencies=[Depends(enforce_auth_rate_limit)])
def reset_password(payload: ResetRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Sets a new password with a one-time reset link (services/password_resets.py).
    Every device is signed out; the person then signs in as usual (2FA included)."""
    try:
        user = password_resets.use(db, payload.token, payload.new_password)
    except password_resets.ResetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")
    _log_event(db, request, "password_reset", user=user)
    return {"status": "password_updated", "username": user.username}


# --------------------------------------------------------------------------
# Authenticated endpoints
# --------------------------------------------------------------------------

@router.get("/me", response_model=UserPublic)
def get_me(user: User = Depends(get_current_user)):
    return UserPublic.from_user(user)


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    db.commit()
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")
    _log_event(db, request, "logout_all", user=user)
    return {"status": "all_sessions_revoked"}


@router.post("/change-password", dependencies=[Depends(enforce_auth_rate_limit)])
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    error = validate_password_strength(payload.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from the current password.")

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = _now()
    # Revoke every existing session (incl. other devices) for safety.
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    db.commit()

    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth")
    _log_event(db, request, "password_changed", user=user)
    return {"status": "password_updated", "message": "Password updated. Please log in again on all devices."}


# --------------------------------------------------------------------------
# Two-Factor Authentication management
# --------------------------------------------------------------------------

@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
def setup_2fa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled.")

    secret = pyotp.random_base32()
    user.totp_secret_encrypted = encrypt_secret(secret)
    user.totp_last_used_step = None
    db.commit()

    issuer = "Current"
    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=issuer)

    qr_img = qrcode.make(otpauth_uri)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=otpauth_uri,
        qr_code_base64=f"data:image/png;base64,{qr_base64}",
    )


@router.post("/2fa/confirm", response_model=TwoFactorConfirmResponse, dependencies=[Depends(enforce_auth_rate_limit)])
def confirm_2fa(
    payload: TwoFactorConfirmRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled.")
    if not user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="Call /2fa/setup first to generate a secret.")

    if not _verify_totp(db, user, payload.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid verification code. Please try again.")

    user.totp_enabled = True
    user.totp_confirmed_at = _now()

    # Clear any pre-existing backup codes and issue a fresh set.
    db.query(BackupCode).filter(BackupCode.user_id == user.id).delete()
    raw_codes = generate_backup_codes()
    for code in raw_codes:
        db.add(BackupCode(user_id=user.id, code_hash=hash_backup_code(code)))
    db.commit()

    _log_event(db, request, "2fa_enabled", user=user)
    return TwoFactorConfirmResponse(backup_codes=raw_codes)


@router.post("/2fa/disable", dependencies=[Depends(enforce_auth_rate_limit)])
def disable_2fa(
    payload: TwoFactorDisableRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect.")
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled.")
    if not _verify_totp_or_backup_code(db, user, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authentication code.")

    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.totp_confirmed_at = None
    user.totp_last_used_step = None
    db.query(BackupCode).filter(BackupCode.user_id == user.id).delete()
    db.commit()

    _log_event(db, request, "2fa_disabled", user=user)
    return {"status": "2fa_disabled"}


@router.post("/2fa/backup-codes/regenerate", response_model=TwoFactorConfirmResponse)
def regenerate_backup_codes(
    payload: BackupCodesRegenerateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect.")
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled.")

    db.query(BackupCode).filter(BackupCode.user_id == user.id).delete()
    raw_codes = generate_backup_codes()
    for code in raw_codes:
        db.add(BackupCode(user_id=user.id, code_hash=hash_backup_code(code)))
    db.commit()

    _log_event(db, request, "backup_codes_regenerated", user=user)
    return TwoFactorConfirmResponse(backup_codes=raw_codes)


# --------------------------------------------------------------------------
# Admin-only user management (household members)
# --------------------------------------------------------------------------

@router.get("/users", response_model=list[UserPublic])
def list_users(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Members of the admin's own household."""
    members = db.query(User).filter(User.household_id == admin.household_id).order_by(User.id).all()
    return [UserPublic.from_user(u) for u in members]


@router.post("/users", response_model=UserPublic)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")

    error = validate_password_strength(payload.password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already in use.")

    user = User(
        household_id=admin.household_id,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _log_event(db, request, "user_created_by_admin", user=user, username_attempted=admin.username)
    return UserPublic.from_user(user)


@router.delete("/users/{user_id}")
def deactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    target = (
        db.query(User)
        .filter(User.id == user_id, User.household_id == admin.household_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    target.is_active = False
    db.query(RefreshToken).filter(RefreshToken.user_id == target.id).update({"revoked": True})
    db.commit()
    return {"status": "deactivated"}


@router.post("/users/{user_id}/clear-lock", response_model=UserPublic)
def clear_lock(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Lets someone sign in from a new device while their account is paused.
    Household admins clear their own members; the instance owner anyone."""
    query = db.query(User).filter(User.id == user_id)
    if not admin.is_superuser:
        query = query.filter(User.household_id == admin.household_id)
    target = query.first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    lockout.clear(db, target)
    _log_event(db, request, "lock_cleared", user=target, username_attempted=admin.username)
    return UserPublic.from_user(target)


@router.post("/users/{user_id}/reset-link", response_model=ResetLinkCreated)
def make_reset_link(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """A one-time link (an hour) that sets a new password: household admins for
    their members, the instance owner for admins. Shown once."""
    target = db.get(User, user_id)
    # Other households' accounts don't exist as far as a household admin can tell.
    if target is None or (not admin.is_superuser and target.household_id != admin.household_id):
        raise HTTPException(status_code=404, detail="User not found.")
    problem = password_resets.why_not(admin, target)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    link, token = password_resets.create(db, target, admin.id)
    _log_event(db, request, "reset_link_created", user=target, username_attempted=admin.username)
    return ResetLinkCreated(token=token, link=password_resets.url(db, token), username=target.username,
                            expires_at=link.expires_at)


@router.get("/other-admins", response_model=list[OtherAdmin])
def list_other_admins(owner: User = Depends(get_current_superuser), db: Session = Depends(get_db)):
    """Admins of the other households, so the instance owner can make them a reset link."""
    admins = (
        db.query(User).join(Household)
        .filter(User.is_admin == True, User.is_active == True, User.household_id != owner.household_id)  # noqa: E712
        .order_by(Household.name, User.username)
        .all()
    )
    return [OtherAdmin(id=u.id, username=u.username, household_name=u.household.name,
                       last_login_at=u.last_login_at, locked_until=lockout.locked_until(u)) for u in admins]


# --------------------------------------------------------------------------
# Invites: the instance owner invites new households, household admins
# invite members of their own household.
# --------------------------------------------------------------------------

def _visible_invites(db: Session, user: User):
    """Invites this user manages: their household's member invites (admins)
    and new-household invites (instance owner)."""
    query = db.query(Invite)
    if user.is_superuser:
        return query.filter((Invite.household_id == user.household_id) | Invite.household_id.is_(None))
    return query.filter(Invite.household_id == user.household_id)


def _invite_read(db: Session, invite: Invite, code: str | None = None) -> InviteRead:
    household = db.get(Household, invite.household_id) if invite.household_id else None
    creator = db.get(User, invite.created_by_id) if invite.created_by_id else None
    used_by = [name for (name,) in db.query(User.username).filter(User.invite_id == invite.id).order_by(User.id)]
    data = dict(
        id=invite.id,
        kind="member" if invite.household_id else "household",
        note=invite.note,
        household_name=household.name if household else None,
        grants_admin=invite.grants_admin,
        max_uses=invite.max_uses,
        use_count=invite.use_count,
        status=invite_service.invite_state(invite),
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        last_used_at=invite.last_used_at,
        created_by=creator.username if creator else None,
        used_by=used_by,
    )
    if code:
        return InviteCreated(**data, code=code, link=invite_service.invite_link(db, code))
    return InviteRead(**data)


@router.get("/invites", response_model=list[InviteRead])
def list_invites(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    invites = _visible_invites(db, admin).order_by(Invite.id.desc()).limit(200).all()
    return [_invite_read(db, i) for i in invites]


@router.post("/invites", response_model=InviteCreated)
def create_invite(
    payload: InviteCreate,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Creates an invite code (returned once). 'household' invites (a new,
    separate household) are for the instance owner only."""
    if payload.kind == "household" and not admin.is_superuser:
        raise HTTPException(status_code=403, detail="Only the instance owner can invite new households.")
    invite, code = invite_service.create_invite(
        db,
        created_by_id=admin.id,
        household_id=admin.household_id if payload.kind == "member" else None,
        note=payload.note,
        expires_in_days=payload.expires_in_days,
        max_uses=payload.max_uses,
        grants_admin=payload.grants_admin,
    )
    _log_event(db, request, f"invite_created_{payload.kind}", user=admin)
    return _invite_read(db, invite, code)


@router.delete("/invites/{invite_id}", response_model=InviteRead)
def revoke_invite(invite_id: int, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    invite = _visible_invites(db, admin).filter(Invite.id == invite_id).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found.")
    invite_service.revoke(db, invite)
    return _invite_read(db, invite)
