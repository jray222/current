import ipaddress
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.security import decode_token, key_state

# `auto_error=False` so we can return a clean 401 with a consistent shape
# instead of FastAPI's default "Not authenticated" on a missing header.
_bearer_scheme = HTTPBearer(auto_error=False)


# Cloudflare's published ranges (https://www.cloudflare.com/ips/, checked
# 2026-10). Requests from them, from private and Docker networks (a tunnel or
# proxy on this machine) and from TRUSTED_PROXIES may say who the visitor is.
_CLOUDFLARE = (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32",
)
_PRIVATE = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7")
_PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in _PRIVATE)


@lru_cache(maxsize=4)
def _proxy_networks(extra: str) -> tuple:
    networks = []
    for cidr in (*_CLOUDFLARE, *_PRIVATE, *extra.split(",")):
        cidr = cidr.strip()
        if cidr:
            try:
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                print(f"[security] Ignoring TRUSTED_PROXIES entry {cidr!r}: not an address or range")
    return tuple(networks)


def _ip(value: str):
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    return ip.ipv4_mapped or ip if ip.version == 6 else ip


def is_private_address(value: str) -> bool:
    ip = _ip(value)
    return bool(ip) and any(ip.version == n.version and ip in n for n in _PRIVATE_NETWORKS)


def is_trusted_proxy(value: str) -> bool:
    ip = _ip(value)
    return bool(ip) and any(ip.version == n.version and ip in n for n in _proxy_networks(settings.TRUSTED_PROXIES))


def get_client_ip(request: Request) -> str:
    """The visitor's IP, for rate limits and lockouts. Behind a proxy you
    control (TRUST_PROXY_HEADERS), every request comes from the proxy, so the
    real address is read from its headers: Cloudflare's CF-Connecting-IP
    first, then X-Real-IP, then X-Forwarded-For. Only a request that comes
    from a proxy address (see _CLOUDFLARE) is believed, so if Dose's port is
    also open to the internet, nobody can make up an address."""
    peer = request.client.host if request.client else "unknown"
    if not (settings.TRUST_PROXY_HEADERS and is_trusted_proxy(peer)):
        return peer
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = (request.headers.get(header) or "").strip()
        if _ip(value):
            return value
    hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if _ip(h)]
    # Proxies append the address they saw, so the nearest hop that isn't a proxy
    # is the visitor; anything left of it could be made up.
    for hop in reversed(hops):
        if not is_trusted_proxy(hop):
            return hop
    return hops[0] if hops else peer


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise unauthorized

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise unauthorized

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise unauthorized

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise unauthorized

    # Access tokens minted before a password change, or before the owner
    # signed everyone out, are no longer valid.
    issued = float(payload.get("t") or payload.get("iat", 0))
    if user.password_changed_at:
        if issued < _as_utc(user.password_changed_at).timestamp():
            raise unauthorized
    if int(payload.get("gen") or 0) < key_state.sessions_generation:
        raise unauthorized

    return user


def get_household_id(user: User = Depends(get_current_user)) -> int:
    """The tenant every data query must be scoped to."""
    return user.household_id


def get_current_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household administrator privileges required.",
        )
    return user


def get_current_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the instance owner can change this setting.",
        )
    return user
