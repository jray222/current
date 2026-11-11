"""Feed discovery, fetching, and parsing using feedparser on safe in-memory bytes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
import time
import urllib.parse
from typing import Optional, Any
import feedparser
from lxml import html as lxml_html

from app.services.safe_fetch import safe_fetch, DEFAULT_USER_AGENT


@dataclass
class FeedEntry:
    title: str
    url: str
    summary: Optional[str]
    author: Optional[str]
    published_at: Optional[datetime]
    image_remote_url: Optional[str]
    tags: list[str]


def clean_html_snippet(raw: Optional[str]) -> str:
    """Removes HTML tags and decodes entities from short snippets like titles or summaries."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_image_from_entry(entry: Any) -> Optional[str]:
    """Extracts candidate image URL from media_content, media_thumbnail, enclosures, or content."""
    # 1. Media content
    media_content = getattr(entry, "media_content", None) or []
    for m in media_content:
        url = m.get("url")
        medium = m.get("medium")
        m_type = m.get("type", "")
        if url and (medium == "image" or m_type.startswith("image/")):
            return url

    # 2. Media thumbnail
    media_thumbnail = getattr(entry, "media_thumbnail", None) or []
    for t in media_thumbnail:
        url = t.get("url")
        if url:
            return url

    # 3. Enclosures
    enclosures = getattr(entry, "enclosures", None) or []
    for enc in enclosures:
        url = enc.get("href") or enc.get("url")
        enc_type = enc.get("type", "")
        if url and enc_type.startswith("image/"):
            return url

    # 4. First <img> tag in content or summary
    candidates = []
    if hasattr(entry, "content") and entry.content:
        for c in entry.content:
            val = c.get("value")
            if val:
                candidates.append(val)
    if hasattr(entry, "summary") and entry.summary:
        candidates.append(entry.summary)

    for body in candidates:
        match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', body, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def parse_feed_bytes(content: bytes, fallback_url: str = "") -> tuple[dict[str, Any], list[FeedEntry]]:
    """Parses feed bytes using feedparser. NEVER pass unverified URLs to feedparser directly."""
    parsed = feedparser.parse(content)
    feed_info = {
        "title": clean_html_snippet(parsed.feed.get("title", "")),
        "link": parsed.feed.get("link", fallback_url),
        "description": clean_html_snippet(parsed.feed.get("description", "")),
        "image": parsed.feed.get("image", {}).get("href"),
    }

    entries: list[FeedEntry] = []
    for e in parsed.entries:
        link = e.get("link") or ""
        if fallback_url and link:
            link = urllib.parse.urljoin(fallback_url, link)
        if not link:
            continue

        title = clean_html_snippet(e.get("title", "Untitled"))
        summary = clean_html_snippet(e.get("summary") or e.get("description") or "")
        author = clean_html_snippet(e.get("author") or "") or None

        # Parse publication date
        published_at = None
        struct_time = e.get("published_parsed") or e.get("updated_parsed")
        if struct_time:
            try:
                published_at = datetime.fromtimestamp(time.mktime(struct_time), tz=timezone.utc).replace(tzinfo=None)
            except Exception:
                published_at = None

        image_url = _extract_image_from_entry(e)
        if image_url and fallback_url:
            image_url = urllib.parse.urljoin(fallback_url, image_url)

        # Tags / categories
        raw_tags = e.get("tags") or []
        tags = [
            clean_html_snippet(t.get("term") or t.get("label") or "")
            for t in raw_tags
            if (t.get("term") or t.get("label"))
        ]

        entries.append(
            FeedEntry(
                title=title,
                url=link,
                summary=summary[:1000] if summary else None,
                author=author[:255] if author else None,
                published_at=published_at,
                image_remote_url=image_url[:1000] if image_url else None,
                tags=tags[:10],
            )
        )

    return feed_info, entries


def discover_feed_urls(html_text: str, base_url: str) -> list[str]:
    """Finds RSS/Atom feed links in an HTML document."""
    found: list[str] = []
    try:
        doc = lxml_html.fromstring(html_text)
        links = doc.xpath('//link[@rel="alternate"]')
        for link in links:
            l_type = (link.get("type") or "").lower()
            href = link.get("href")
            if not href:
                continue
            if (
                "application/rss+xml" in l_type
                or "application/atom+xml" in l_type
                or "application/feed+json" in l_type
                or "text/xml" in l_type
            ):
                full = urllib.parse.urljoin(base_url, href)
                if full not in found:
                    found.append(full)
    except Exception:
        pass

    return found


def fetch_and_parse_feed(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    max_bytes: int = 5 * 1024 * 1024,
) -> tuple[dict[str, Any], list[FeedEntry], str]:
    """Safely fetches a feed URL, auto-discovering the feed if given an HTML landing page.
    Returns (feed_info, entries, final_feed_url).
    """
    res = safe_fetch(url, user_agent=user_agent, max_bytes=max_bytes)

    # Check if the fetched content is HTML rather than XML/RSS
    content_type = res.headers.get("content-type", "").lower()
    is_html = "text/html" in content_type or res.text.strip().startswith(("<!DOCTYPE html", "<html"))

    if is_html:
        discovered = discover_feed_urls(res.text, res.url)
        if discovered:
            feed_url = discovered[0]
            feed_res = safe_fetch(feed_url, user_agent=user_agent, max_bytes=max_bytes)
            info, entries = parse_feed_bytes(feed_res.content, fallback_url=feed_url)
            return info, entries, feed_url

    info, entries = parse_feed_bytes(res.content, fallback_url=res.url)
    return info, entries, res.url
