import re
from typing import Literal, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    household_name: Optional[str] = None
    # Required once the instance is invite-only (after the first account).
    invite_code: Optional[str] = Field(default=None, max_length=64)

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-32 characters and contain only letters, "
                "numbers, dots, dashes, or underscores."
            )
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class MFARequiredResponse(BaseModel):
    mfa_required: bool = True
    mfa_token: str


class FailedAttempts(BaseModel):
    """Failed sign-ins to this account since its last sign-in (shown once)."""
    count: int
    addresses: int
    last_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserPublic"
    failed_attempts: Optional[FailedAttempts] = None


class VerifyMFARequest(BaseModel):
    mfa_token: str
    code: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserPublic(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool
    is_superuser: bool = False
    is_active: bool = True
    totp_enabled: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    household_id: int
    household_name: str
    # Sign-in from new devices is paused until then (services/lockout.py).
    locked_until: Optional[datetime] = None

    @classmethod
    def from_user(cls, user) -> "UserPublic":
        from app.services.lockout import locked_until
        household = user.household
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            is_admin=user.is_admin,
            is_superuser=user.is_superuser,
            is_active=user.is_active,
            totp_enabled=user.totp_enabled,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            household_id=household.id,
            household_name=household.name,
            locked_until=locked_until(user),
        )


class BootstrapStatus(BaseModel):
    # True when no account exists yet: the first sign-up becomes instance owner.
    setup_required: bool
    # Anyone may sign up without an invite.
    registration_open: bool
    # Sign-up needs an invite code (the sign-in page offers "I have an invite").
    invite_only: bool = False


class InviteCreate(BaseModel):
    # 'household': a new household of their own (instance owner only).
    # 'member': joins your household (household admins).
    kind: Literal["household", "member"]
    note: Optional[str] = Field(default=None, max_length=100)
    expires_in_days: int = Field(default=7, ge=1, le=90)
    max_uses: int = Field(default=1, ge=1, le=25)
    grants_admin: bool = False


class InviteRead(BaseModel):
    id: int
    kind: Literal["household", "member"]
    note: Optional[str] = None
    household_name: Optional[str] = None
    grants_admin: bool
    max_uses: int
    use_count: int
    status: Literal["active", "used", "expired", "revoked"]
    expires_at: datetime
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_by: Optional[str] = None
    used_by: List[str] = []


class InviteCreated(InviteRead):
    # Shown once: only a hash is stored.
    code: str
    # The link on the public address (PUBLIC_URL / owner setting), if one is set.
    link: Optional[str] = None


class InviteCheck(BaseModel):
    valid: bool
    kind: Optional[Literal["household", "member"]] = None
    household_name: Optional[str] = None
    expires_at: Optional[datetime] = None


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code_base64: str


class TwoFactorConfirmRequest(BaseModel):
    code: str


class TwoFactorConfirmResponse(BaseModel):
    backup_codes: List[str]


class TwoFactorDisableRequest(BaseModel):
    password: str
    code: str


class BackupCodesRegenerateRequest(BaseModel):
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-32 characters and contain only letters, "
                "numbers, dots, dashes, or underscores."
            )
        return v


class ResetLinkCreated(BaseModel):
    # Shown once: only a hash is stored.
    token: str
    # The link on the public address, if one is set (else the app adds the address it's open on).
    link: Optional[str] = None
    username: str
    expires_at: datetime


class ResetCheck(BaseModel):
    valid: bool
    username: Optional[str] = None
    expires_at: Optional[datetime] = None


class ResetRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class OtherAdmin(BaseModel):
    """An admin of another household, for the instance owner's reset links."""
    id: int
    username: str
    household_name: str
    last_login_at: Optional[datetime] = None
    locked_until: Optional[datetime] = None


class IdentityCheck(BaseModel):
    """Your password again (and a two-step code, if it's on) before something that can't be taken back."""
    password: str = Field(min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, max_length=32)


TokenResponse.model_rebuild()
