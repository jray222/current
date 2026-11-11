import secrets
import warnings
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve paths relative to the backend/ directory so the app behaves the same
# no matter which working directory uvicorn is launched from.
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
_SECRET_KEY_FILE = DATA_DIR / "secret_key"


def _load_or_create_secret_key() -> str:
    """
    Returns a stable signing/encryption key when SECRET_KEY isn't configured.

    The key protects JWTs *and* the at-rest encryption of TOTP secrets and the
    stored Anthropic key, so it must survive restarts - a per-process random key would
    silently lock every 2FA user out after the first restart.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _SECRET_KEY_FILE.exists():
        key = _SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(64)
    _SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    return key


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DEBUG: bool = False
    DATABASE_URL: str = f"sqlite:///{(DATA_DIR / 'current.db').as_posix()}"

    # --- Authentication & Security ---
    # Signs sign-ins (JWTs and known-device cookies). Until DATA_KEYS is set
    # and the owner re-encrypts (Account menu -> Server keys), it also derives
    # the key that encrypts 2FA secrets and the stored Anthropic API key. If unset, a key is generated once and
    # persisted to backend/data/secret_key.
    SECRET_KEY: str = ""
    # Encryption keys for that data, comma-separated, newest first: the newest
    # encrypts and any of them decrypts. Each is a Fernet key (Server keys can
    # make one). Empty = the key derived from SECRET_KEY, as before.
    DATA_KEYS: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MFA_CHALLENGE_EXPIRE_MINUTES: int = 5

    # Account lockout / brute-force protection
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # Only trust X-Forwarded-For when running behind a reverse proxy you
    # control; otherwise any client could spoof its IP to dodge rate limits.
    # Even then, the headers are only read from Cloudflare's addresses, private
    # and Docker networks, and TRUSTED_PROXIES (comma-separated addresses or
    # ranges such as 203.0.113.10 or 203.0.113.0/24).
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXIES: str = ""

    # Default sign-up mode. False = invite only: after the first account, new
    # accounts need an invite link from the instance owner (a new household)
    # or a household admin (joins their household). True = anyone can sign up
    # and gets their own household. The instance owner can switch this at
    # runtime in the account menu (stored in runtime_config).
    ALLOW_REGISTRATION: bool = False
    INVITE_DEFAULT_DAYS: int = 7

    # Frontend origin allowed to talk to the API (CORS). A wildcard cannot be
    # used together with credentialed (cookie-based) requests.
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # The address people use to reach this Current from the internet, e.g.
    # https://current.example.com (behind Cloudflare or another proxy). Invite
    # links are built from it. The instance owner can also set it in the app.
    PUBLIC_URL: str = ""

    REFRESH_COOKIE_NAME: str = "current_refresh_token"

    # Directory of the built frontend (index.html + assets/). When set, the
    # API process also serves the UI - used by the Docker image.
    FRONTEND_DIST: str = ""

    # The time zone dates are worked out in, e.g. America/Indiana/Indianapolis (the
    # usual TZ variable). Unset: this machine's zone, else UTC.
    TZ: str = ""

    # --- AI (Anthropic is the provider; everything works without a key) ---
    # The owner can store a key in the app instead (encrypted, Settings -> AI).
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5-5"

    # --- Current News Crawler, Safe Fetch & Reader settings ---
    # Sent with outbound crawler requests: Current/0.1 (+PUBLIC_URL; CRAWLER_CONTACT)
    CRAWLER_CONTACT: str = "https://github.com/jray222/current"
    RESPECT_ROBOTS: bool = True
    CRAWL_DELAY_SECONDS: float = 1.0
    MAX_NEW_PER_SOURCE: int = 25
    MAX_ARTICLE_PAGES: int = 5
    RETENTION_DAYS: int = 14
    BROWSER_FETCH: bool = True
    ADBLOCK_EXTRA_HOSTS: str = ""
    ALLOW_PRIVATE_SOURCES: bool = False
    ALLOWED_PORTS: str = ""
    SCHEDULER_ENABLED: bool = True

    # Where downloaded article thumbnails live: <IMAGES_DIR>/<household>/<yyyy-mm>/...
    # Default backend/data/images.
    IMAGES_DIR: str = ""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where SECRET_KEY came from: "environment" or "file" (shown in Server keys).
    _secret_key_source: str = "environment"

    def model_post_init(self, __context) -> None:
        if not self.SECRET_KEY:
            self.SECRET_KEY = _load_or_create_secret_key()
            self._secret_key_source = "file"
        elif self.APP_ENV == "production" and len(self.SECRET_KEY) < 32:
            warnings.warn(
                "SECRET_KEY is too short for a production deployment. "
                "Set a strong, randomly generated SECRET_KEY in backend/.env."
            )

    @property
    def images_dir(self) -> Path:
        return Path(self.IMAGES_DIR) if self.IMAGES_DIR else DATA_DIR / "images"

    @property
    def secret_key_source(self) -> str:
        return self._secret_key_source

    @property
    def secret_key_file(self) -> Path:
        return _SECRET_KEY_FILE


settings = Settings()
