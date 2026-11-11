"""Article link discovery on listing pages and metadata extraction from HTML.
"""
from datetime import datetime, timezone
import json
import re
import urllib.parse
from typing import Optional, Any
from dateutil import parser as date_parser
from lxml import html as lxml_html

from app.services.feeds import clean_html_snippet
from app.services.dedupe import canonical_url

NON_ARTICLE_PATTERNS = re.compile(
    r"/(category|categories|tag|tags|author|authors|user|users|topic|topics|"
    r"login|signup|signin|signout|register|privacy|terms|about|contact|"
    r"subscribe|search|feed|rss|wp-content|wp-admin|archive|pages?)(/|[-_.]|$)",
    re.IGNORECASE,
)

DATE_IN_PATH = re.compile(r"/20[12]\d[/-]\d{1,2}[/-]\d{1,2}/")
SLUG_OR_ID = re.compile(r"/[a-z0-9_-]+-[a-z0-9_-]+|\d{5,}")


def extract_article_links(
    html_text: str,
    base_url: str,
    link_pattern: Optional[str] = None,
    link_selector: Optional[str] = None,
) -> list[str]:
    """Finds candidate article links on an HTML listing page."""
    if not html_text:
        return []

    try:
        doc = lxml_html.fromstring(html_text)
    except Exception:
        return []

    base_parsed = urllib.parse.urlparse(base_url)
    base_host = base_parsed.netloc.lower().removeprefix("www.")

    anchors = []
    if link_selector:
        try:
            anchors = doc.cssselect(link_selector)
        except Exception:
            anchors = doc.xpath(f"//{link_selector}")
    else:
        anchors = doc.xpath("//a[@href]")

    pattern_re = re.compile(link_pattern, re.IGNORECASE) if link_pattern else None

    seen_canonical = set()
    results = []

    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        href = href.strip()
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full_url)
        target_host = parsed.netloc.lower().removeprefix("www.")

        # Discard cross-domain links
        if not (target_host == base_host or target_host.endswith("." + base_host)):
            continue

        path = parsed.path
        if not path or path == "/":
            continue

        # If user specified a pattern, follow that
        if pattern_re:
            if not pattern_re.search(full_url):
                continue
        elif not link_selector:
            # Automatic heuristic filtering
            if NON_ARTICLE_PATTERNS.search(path):
                continue

            link_text = clean_html_snippet(a.text_content())
            # Headline-style link or URL slug heuristic
            has_slug_or_date = bool(DATE_IN_PATH.search(path) or SLUG_OR_ID.search(path))
            has_descriptive_text = len(link_text) >= 15

            if not (has_slug_or_date or has_descriptive_text):
                continue

        c_url = canonical_url(full_url)
        if c_url not in seen_canonical:
            seen_canonical.add(c_url)
            results.append(full_url)

    return results


def _parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = date_parser.parse(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def extract_meta(html_text: str, page_url: str) -> dict[str, Any]:
    """Extracts article metadata (title, summary, author, date, image, amp) from HTML
    using JSON-LD, OpenGraph, Twitter Cards, and semantic HTML tags.
    """
    result: dict[str, Any] = {
        "title": "",
        "summary": None,
        "author": None,
        "published_at": None,
        "image_remote_url": None,
        "amp_url": None,
        "feed_tags": [],
    }

    if not html_text:
        return result

    try:
        doc = lxml_html.fromstring(html_text)
    except Exception:
        return result

    # --------------------------------------------------------------------------
    # 1. JSON-LD Structured Data
    # --------------------------------------------------------------------------
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        try:
            content = script.text_content().strip()
            if not content:
                continue
            data = json.loads(content)
            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if not isinstance(item, dict):
                    continue
                type_val = item.get("@type", "")
                types = type_val if isinstance(type_val, list) else [type_val]
                if any(t in ("NewsArticle", "Article", "BlogPosting", "TechArticle", "Report", "WebPage") for t in types):
                    if not result["title"] and item.get("headline"):
                        result["title"] = clean_html_snippet(item["headline"])
                    if not result["summary"] and item.get("description"):
                        result["summary"] = clean_html_snippet(item["description"])
                    if not result["published_at"]:
                        date_str = item.get("datePublished") or item.get("dateCreated") or item.get("dateModified")
                        result["published_at"] = _parse_datetime(date_str)
                    if not result["author"]:
                        author_data = item.get("author")
                        if isinstance(author_data, dict):
                            result["author"] = clean_html_snippet(author_data.get("name"))
                        elif isinstance(author_data, list) and author_data and isinstance(author_data[0], dict):
                            result["author"] = clean_html_snippet(author_data[0].get("name"))
                        elif isinstance(author_data, str):
                            result["author"] = clean_html_snippet(author_data)
                    if not result["image_remote_url"]:
                        img_data = item.get("image")
                        if isinstance(img_data, str):
                            result["image_remote_url"] = urllib.parse.urljoin(page_url, img_data)
                        elif isinstance(img_data, dict) and img_data.get("url"):
                            result["image_remote_url"] = urllib.parse.urljoin(page_url, img_data["url"])
                        elif isinstance(img_data, list) and img_data and isinstance(img_data[0], str):
                            result["image_remote_url"] = urllib.parse.urljoin(page_url, img_data[0])
                    if not result["feed_tags"] and item.get("keywords"):
                        kw = item["keywords"]
                        if isinstance(kw, str):
                            result["feed_tags"] = [k.strip() for k in kw.split(",") if k.strip()][:10]
                        elif isinstance(kw, list):
                            result["feed_tags"] = [str(k).strip() for k in kw if str(k).strip()][:10]
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # 2. OpenGraph & Twitter Meta Tags
    # --------------------------------------------------------------------------
    meta_tags = doc.xpath("//meta")
    og_data: dict[str, str] = {}
    for m in meta_tags:
        prop = m.get("property") or m.get("name") or ""
        prop = prop.strip().lower()
        val = m.get("content") or ""
        if prop and val:
            og_data[prop] = val.strip()

    if not result["title"]:
        candidate_title = og_data.get("og:title") or og_data.get("twitter:title")
        if candidate_title:
            result["title"] = clean_html_snippet(candidate_title)

    if not result["summary"]:
        candidate_summary = og_data.get("og:description") or og_data.get("twitter:description") or og_data.get("description")
        if candidate_summary:
            result["summary"] = clean_html_snippet(candidate_summary)[:1000]

    if not result["image_remote_url"]:
        candidate_image = og_data.get("og:image") or og_data.get("twitter:image")
        if candidate_image:
            result["image_remote_url"] = urllib.parse.urljoin(page_url, candidate_image)[:1000]

    if not result["published_at"]:
        date_str = og_data.get("article:published_time") or og_data.get("og:article:published_time") or og_data.get("date")
        if date_str:
            result["published_at"] = _parse_datetime(date_str)

    if not result["author"]:
        author_str = og_data.get("article:author") or og_data.get("author") or og_data.get("twitter:creator")
        if author_str:
            result["author"] = clean_html_snippet(author_str)[:255]

    # --------------------------------------------------------------------------
    # 3. HTML Tags (title, time, amp link)
    # --------------------------------------------------------------------------
    if not result["title"]:
        title_elems = doc.xpath("//title")
        if title_elems and title_elems[0].text:
            result["title"] = clean_html_snippet(title_elems[0].text)

    if not result["published_at"]:
        time_elems = doc.xpath("//time[@datetime]")
        if time_elems:
            result["published_at"] = _parse_datetime(time_elems[0].get("datetime"))

    amp_links = doc.xpath('//link[@rel="amphtml"]')
    if amp_links:
        amp_href = amp_links[0].get("href")
        if amp_href:
            result["amp_url"] = urllib.parse.urljoin(page_url, amp_href)[:1000]

    if not result["title"]:
        result["title"] = "Untitled Article"

    return result
