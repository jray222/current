"""Playwright Chromium headless browser session with route guarding, ad-blocking,
and SSRF protection for JavaScript-rendered sites.
"""
import os
import threading
import urllib.parse
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, Playwright, Route, Request

from app.services.adblock import is_ad_host
from app.services.safe_fetch import validate_url_and_dns, SSRFBlockedError

_local = threading.local()
_all_locals_lock = threading.Lock()
_all_playwrights: list[Playwright] = []


def _get_browser() -> Browser:
    """Returns a thread-local headless Chromium browser instance."""
    if not hasattr(_local, "browser") or _local.browser is None or not _local.browser.is_connected():
        p = sync_playwright().start()
        b = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        _local.playwright = p
        _local.browser = b
        with _all_locals_lock:
            _all_playwrights.append(p)
    return _local.browser


def _route_handler(route: Route, request: Request, block_ads: bool = True) -> None:
    """Guards every browser request against SSRF, tracking beacons, and ad networks.
    Manually inspects HTTP redirects with max_redirects=0 to ensure redirected destinations
    do not bypass SSRF checks to access internal or loopback IP addresses.
    """
    url = request.url
    resource_type = request.resource_type

    # Block media/fonts to save CPU/memory and prevent image-beacon telemetry
    if resource_type in ("image", "media", "font"):
        route.abort("blockedbyclient")
        return

    # Check Ad / tracker hosts
    if block_ads and is_ad_host(url):
        route.abort("blockedbyclient")
        return

    # Initial SSRF guard on outbound target
    try:
        validate_url_and_dns(url)
    except Exception:
        route.abort("blockedbyclient")
        return

    # For navigation and main subrequests, follow redirects manually with max_redirects=0
    # to intercept and validate any 30x redirect locations before connecting
    try:
        current_url = url
        hops = 0
        while hops < 5:
            response = route.fetch(max_redirects=0, url=current_url)
            if response.status in (301, 302, 303, 307, 308):
                loc = response.headers.get("location")
                if not loc:
                    route.fulfill(response=response)
                    return
                next_url = urllib.parse.urljoin(current_url, loc)
                # Re-validate every redirect hop against private/loopback/metadata IPs
                validate_url_and_dns(next_url)
                current_url = next_url
                hops += 1
            else:
                route.fulfill(response=response)
                return

        route.abort("blockedbyclient")
    except Exception:
        route.abort("blockedbyclient")


def fetch_page_content(
    url: str,
    timeout_ms: int = 25000,
    block_ads: bool = True,
    wait_selector: Optional[str] = None,
) -> str:
    """Loads a URL using headless Chromium, executing page JavaScript and returning
    the rendered HTML content.
    """
    # Pre-validate target URL before opening in browser
    validate_url_and_dns(url)

    browser = _get_browser()
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Current/1.0",
        viewport={"width": 1280, "height": 800},
        java_script_enabled=True,
    )

    # Disable WebSockets and WebRTC to prevent script-initiated socket connections to loopback/intranet
    context.add_init_script("delete window.WebSocket; delete window.RTCPeerConnection;")

    try:
        page = context.new_page()
        page.route("**/*", lambda route, req: _route_handler(route, req, block_ads=block_ads))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Post-navigation validation of final landing URL
            validate_url_and_dns(page.url)

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=5000)
                except Exception:
                    pass
            content = page.content()
            return content
        finally:
            page.close()
    finally:
        context.close()


def close_browser() -> None:
    """Closes all thread-local browser processes."""
    if hasattr(_local, "browser") and _local.browser is not None:
        try:
            _local.browser.close()
        except Exception:
            pass
        _local.browser = None
    if hasattr(_local, "playwright") and _local.playwright is not None:
        try:
            _local.playwright.stop()
        except Exception:
            pass
        _local.playwright = None

    with _all_locals_lock:
        for p in _all_playwrights:
            try:
                p.stop()
            except Exception:
                pass
        _all_playwrights.clear()
