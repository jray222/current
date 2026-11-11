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

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_browser_lock = threading.Lock()


def _get_browser() -> Browser:
    """Returns a shared headless Chromium browser instance."""
    global _playwright, _browser
    with _browser_lock:
        if _browser is None or not _browser.is_connected():
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
        return _browser


def _route_handler(route: Route, request: Request, block_ads: bool = True) -> None:
    """Guards every browser request against SSRF, tracking beacons, and ad networks."""
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

    # SSRF guard on outbound browser network hops
    try:
        validate_url_and_dns(url)
    except SSRFBlockedError:
        route.abort("blockedbyclient")
        return
    except Exception:
        # If DNS fails or other error, abort safely
        route.abort("blockedbyclient")
        return

    route.continue_()


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

    try:
        page = context.new_page()
        page.route("**/*", lambda route, req: _route_handler(route, req, block_ads=block_ads))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
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
    """Closes the shared browser process."""
    global _playwright, _browser
    with _browser_lock:
        if _browser is not None:
            try:
                _browser.close()
            except Exception:
                pass
            _browser = None
        if _playwright is not None:
            try:
                _playwright.stop()
            except Exception:
                pass
            _playwright = None
