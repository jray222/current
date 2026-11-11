"""Safe HTTP client with SSRF protection, redirect verification, size limits,
robots.txt caching, and polite per-host throttling.
"""
import ipaddress
import os
import socket
import threading
import time
import urllib.parse
import urllib.robotparser
from typing import Optional, NamedTuple
import httpx

DEFAULT_USER_AGENT = "Current/1.0 (+https://github.com/jray222/current)"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_TIMEOUT = 15.0  # seconds
MAX_REDIRECTS = 5

_CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")


class SSRFBlockedError(Exception):
    """Raised when a requested host or redirect target resolves to a private or disallowed IP."""
    pass


class ContentTooLargeError(Exception):
    """Raised when response body exceeds max_bytes."""
    pass


class FetchResponse(NamedTuple):
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    text: str


def is_ip_allowed(ip_str: str) -> bool:
    """Returns True if IP address is a public, routable IP, False if private, loopback, link-local, etc."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in _CARRIER_GRADE_NAT)
    ):
        return False

    return True


def validate_url_and_dns(url: str, allow_custom_ports: bool = False) -> urllib.parse.ParseResult:
    """Validates URL scheme and resolves hostname to ensure every IP is public."""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Unsupported URL scheme: {scheme!r}. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL has no hostname.")

    port = parsed.port or (443 if scheme == "https" else 80)
    if not allow_custom_ports and port not in (80, 443, 8080, 8443):
        # Allow standard web ports, block suspicious internal ports
        raise SSRFBlockedError(f"Disallowed destination port: {port}")

    # Check if hostname itself is a raw IP literal
    try:
        ip_direct = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        ip_direct = None

    if ip_direct is not None:
        if not is_ip_allowed(str(ip_direct)):
            raise SSRFBlockedError(f"Direct IP access to private/reserved IP blocked: {hostname}")
        return parsed

    # Resolve all IPs via DNS
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFBlockedError(f"DNS resolution failed for {hostname}: {e}")

    if not addr_info:
        raise SSRFBlockedError(f"No IP addresses resolved for {hostname}")

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        if not is_ip_allowed(ip_str):
            raise SSRFBlockedError(f"Host '{hostname}' resolved to disallowed private/reserved IP: {ip_str}")

    return parsed


# --------------------------------------------------------------------------
# Per-Host Polite Throttling
# --------------------------------------------------------------------------

class HostThrottle:
    """Ensures polite intervals between requests to the same host."""

    def __init__(self, default_interval_seconds: float = 1.0):
        self.default_interval = default_interval_seconds
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait_for_host(self, host: str, min_interval: Optional[float] = None) -> None:
        interval = self.default_interval if min_interval is None else min_interval
        # Disable throttle in tests for speed
        if os.environ.get("JOB_QUEUE") == "manual" or os.environ.get("TESTING") == "True":
            return

        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(host, 0.0)
            elapsed = now - last
            if elapsed < interval:
                sleep_needed = interval - elapsed
            else:
                sleep_needed = 0.0
            self._last_call[host] = now + sleep_needed

        if sleep_needed > 0:
            time.sleep(sleep_needed)

    def reset(self) -> None:
        with self._lock:
            self._last_call.clear()


throttle = HostThrottle()


# --------------------------------------------------------------------------
# Robots.txt Cache
# --------------------------------------------------------------------------

class RobotsCache:
    """In-memory cache for parsed robots.txt rules per host with 24-hour TTL."""

    def __init__(self, ttl_seconds: float = 86400.0):
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.netloc.lower()
            if not host:
                return True
        except Exception:
            return True

        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(host)
            if cached and (now - cached[0] < self.ttl):
                return cached[1].can_fetch(user_agent, url)

        # Need to fetch robots.txt
        parser = urllib.robotparser.RobotFileParser()
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            res = safe_fetch(
                robots_url,
                max_bytes=256 * 1024,
                timeout=5.0,
                check_robots=False,
                user_agent=user_agent,
            )
            if res.status_code == 200:
                parser.parse(res.text.splitlines())
            else:
                # 404 or other HTTP error implies no robots restrictions
                parser.allow_all = True
        except Exception:
            # If robots.txt cannot be fetched or resolved, default to allow
            parser.allow_all = True

        with self._lock:
            self._cache[host] = (now, parser)

        return parser.can_fetch(user_agent, url)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


robots = RobotsCache()


# --------------------------------------------------------------------------
# Safe Fetch
# --------------------------------------------------------------------------

def safe_fetch(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
    check_robots: bool = True,
    throttle_interval: Optional[float] = None,
) -> FetchResponse:
    """Fetches a URL safely, enforcing SSRF guards on every redirect hop, size caps,
    robots.txt rules, and host throttling.
    """
    current_url = url

    if check_robots and not robots.is_allowed(current_url, user_agent=user_agent):
        raise ValueError(f"Fetching {current_url} is disallowed by site robots.txt rules.")

    req_headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    }
    if headers:
        req_headers.update(headers)

    redirects_followed = 0

    while True:
        # Validate SSRF on current hop
        parsed = validate_url_and_dns(current_url)

        # Host throttling
        throttle.wait_for_host(parsed.netloc.lower(), min_interval=throttle_interval)

        client_timeout = httpx.Timeout(timeout, connect=timeout)

        # We set follow_redirects=False to manually inspect every redirect hop
        with httpx.Client(follow_redirects=False, timeout=client_timeout) as client:
            try:
                response = client.send(
                    client.build_request("GET", current_url, headers=req_headers),
                    stream=True,
                )
            except Exception as e:
                raise e

            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError(f"HTTP {response.status_code} redirect without Location header.")

                    redirects_followed += 1
                    if redirects_followed > MAX_REDIRECTS:
                        raise ValueError(f"Exceeded maximum redirect limit ({MAX_REDIRECTS}).")

                    next_url = urllib.parse.urljoin(current_url, location)
                    current_url = next_url
                    continue

                # Stream response body up to max_bytes
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=32768):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ContentTooLargeError(
                            f"Response size exceeded limit of {max_bytes} bytes."
                        )

                raw_bytes = bytes(content)
                encoding = response.encoding or "utf-8"
                try:
                    text_str = raw_bytes.decode(encoding, errors="replace")
                except Exception:
                    text_str = raw_bytes.decode("utf-8", errors="replace")

                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                return FetchResponse(
                    url=current_url,
                    status_code=response.status_code,
                    headers=resp_headers,
                    content=raw_bytes,
                    text=text_str,
                )
            finally:
                response.close()
