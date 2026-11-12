"""On-demand full-text extractor with multi-method ladder (HTTP -> AMP -> Browser),
structured block parsing, boilerplate cleanup, and paywall detection.
"""
from datetime import datetime, timezone
import json
import logging
import re
import urllib.parse
from typing import Optional, Any
from lxml import etree, html as lxml_html
import trafilatura

from app.database import SessionLocal
from app.models.news import Article, Source
from app.services import job_queue
from app.services.adblock import is_boilerplate_text
from app.services.safe_fetch import safe_fetch

logger = logging.getLogger("current.fulltext")

PAYWALL_PHRASES = [
    "subscribe to continue reading",
    "exclusive to subscribers",
    "to read the full story",
    "already a subscriber",
    "you have reached your limit of free articles",
    "sign in to read the full article",
    "become a member to continue",
    "purchase a digital subscription",
    "this article is for subscribers only",
]


def clean_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Removes empty blocks, boilerplate phrases, and duplicate consecutive text."""
    cleaned: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    for b in blocks:
        b_type = b.get("t")
        if b_type in ("p", "h2", "h3", "blockquote"):
            text = (b.get("x") or "").strip()
            if not text:
                continue
            if is_boilerplate_text(text):
                continue
            # Deduplicate identical paragraphs within the same article
            lower_sig = text.lower()[:80]
            if lower_sig in seen_texts:
                continue
            seen_texts.add(lower_sig)
            cleaned.append({"t": b_type, "x": text})

        elif b_type in ("ul", "ol"):
            raw_items = b.get("items") or []
            valid_items = [
                item.strip() for item in raw_items
                if item and item.strip() and not is_boilerplate_text(item)
            ]
            if valid_items:
                cleaned.append({"t": b_type, "items": valid_items})

        elif b_type == "figure":
            src = b.get("src")
            if src:
                cleaned.append({
                    "t": "figure",
                    "src": src,
                    "caption": (b.get("caption") or "").strip(),
                })

        elif b_type == "story_card":
            title = (b.get("title") or "").strip()
            url = (b.get("url") or "").strip()
            if title and url:
                c_url = b.get("url")
                if c_url not in seen_texts:
                    seen_texts.add(c_url)
                    cleaned.append({
                        "t": "story_card",
                        "title": title,
                        "url": url,
                        "summary": (b.get("summary") or "").strip() or None,
                        "image": (b.get("image") or "").strip() or None,
                        "source": (b.get("source") or "").strip() or None,
                    })

        elif b_type == "collection_header":
            cleaned.append(b)

    return cleaned


def extract_collection_stories(html_text: str, base_url: str) -> list[dict[str, Any]]:
    """Extracts curated story cards from collection / digest / roundup pages."""
    if not html_text or not base_url:
        return []

    try:
        doc = lxml_html.fromstring(html_text)
    except Exception:
        return []

    from app.services.dedupe import canonical_url

    scope = doc.xpath("//main | //article")
    scope_elem = scope[0] if scope else doc

    candidates = scope_elem.xpath(
        './/div[contains(@class, "PagePromo")] | .//article | .//div[contains(@class, "story")] | .//div[contains(@class, "card")] | .//div[contains(@class, "item")]'
    )
    if not candidates and scope_elem != doc:
        candidates = doc.xpath('.//div[contains(@class, "PagePromo")] | .//article')

    seen_urls: set[str] = set()
    stories: list[dict[str, Any]] = []

    for c in candidates:
        anchors = c.xpath('.//h2//a | .//h3//a | .//h4//a | .//*[contains(@class, "title") or contains(@class, "Title")]//a | .//a[contains(@class, "title") or contains(@class, "Title")]')
        if not anchors:
            for a in c.xpath('.//a[@href]'):
                t = (a.text_content() or "").strip()
                if len(t) > 20:
                    anchors = [a]
                    break
        if not anchors:
            continue

        a = anchors[0]
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full_url)
        path = parsed.path.lower()

        # Discard non-story / section / hub urls
        if not ("/article/" in path or "/story/" in path or "/202" in path or "-" in path):
            continue
        if path.endswith(("/world-news", "/us-news", "/politics", "/sports", "/business", "/entertainment")):
            continue

        c_url = canonical_url(full_url)
        if c_url in seen_urls:
            continue

        title = (a.text_content() or "").strip()
        if len(title) < 15 or is_boilerplate_text(title):
            continue

        desc_elems = c.xpath('.//*[contains(@class, "description") or contains(@class, "Description") or contains(@class, "dek") or contains(@class, "summary")] | .//p')
        desc = ""
        if desc_elems:
            desc = (desc_elems[0].text_content() or "").strip()
            if desc == title or is_boilerplate_text(desc):
                desc = ""

        img_elems = c.xpath('.//img/@src | .//img/@data-src | .//img/@data-lazy-src')
        img = img_elems[0].strip() if img_elems else None
        if img and img.startswith("data:"):
            img = None

        seen_urls.add(c_url)
        stories.append({
            "t": "story_card",
            "title": title,
            "url": full_url,
            "summary": desc if desc else None,
            "image": img,
        })

    return stories


def to_blocks_from_html(
    html_text: str,
    custom_selector: Optional[str] = None,
    page_url: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Converts HTML text into structured blocks (paragraphs, headings, lists, quotes)."""
    if not html_text:
        return []

    blocks: list[dict[str, Any]] = []

    # 1. Trafilatura XML extraction
    try:
        xml_output = trafilatura.extract(
            html_text,
            output_format="xml",
            include_formatting=True,
            include_links=False,
            include_images=False,
        )
        if xml_output:
            root = etree.fromstring(xml_output.encode("utf-8"))
            for elem in root.iter():
                tag = elem.tag.lower()
                text = (elem.text or "").strip()
                if tag in ("head", "h1", "h2", "h3"):
                    if text:
                        blocks.append({"t": "h2", "x": text})
                elif tag == "p":
                    if text:
                        blocks.append({"t": "p", "x": text})
                elif tag == "quote":
                    if text:
                        blocks.append({"t": "blockquote", "x": text})
                elif tag == "list":
                    items = [
                        (li.text or "").strip()
                        for li in elem.findall("item")
                        if (li.text or "").strip()
                    ]
                    if items:
                        blocks.append({"t": "ul", "items": items})
    except Exception:
        pass

    # 2. Fallback to direct lxml parsing if trafilatura produced sparse results
    if len(blocks) < 3:
        blocks.clear()
        try:
            doc = lxml_html.fromstring(html_text)
            root_elem = None
            if custom_selector:
                try:
                    candidates = doc.cssselect(custom_selector)
                    if candidates:
                        root_elem = candidates[0]
                except Exception:
                    pass

            if root_elem is None:
                candidates = doc.xpath("//article | //main | //div[contains(@class, 'article-body') or contains(@class, 'post-content')]")
                root_elem = candidates[0] if candidates else doc.body

            if root_elem is not None:
                for elem in root_elem.iterdescendants():
                    tag = elem.tag.lower() if isinstance(elem.tag, str) else ""
                    text = (elem.text_content() or "").strip()
                    if tag in ("h1", "h2", "h3", "h4"):
                        if text:
                            blocks.append({"t": "h2", "x": text})
                    elif tag == "p":
                        if text:
                            blocks.append({"t": "p", "x": text})
                    elif tag == "blockquote":
                        if text:
                            blocks.append({"t": "blockquote", "x": text})
                    elif tag in ("ul", "ol"):
                        items = [
                            (li.text_content() or "").strip()
                            for li in elem.xpath("./li")
                            if (li.text_content() or "").strip()
                        ]
                        if items:
                            blocks.append({"t": tag, "items": items})
        except Exception:
            pass

    # 3. Check if page is a curated collection / roundup of stories
    p_count = sum(1 for b in blocks if b.get("t") == "p")
    if p_count <= 3 and page_url:
        collection_stories = extract_collection_stories(html_text, page_url)
        if len(collection_stories) >= 3:
            result_blocks: list[dict[str, Any]] = []
            intro_p = [b for b in blocks if b.get("t") == "p"][:1]
            if intro_p:
                result_blocks.extend(intro_p)
            result_blocks.append({
                "t": "collection_header",
                "title": "Stories in this Collection",
                "count": len(collection_stories),
            })
            result_blocks.extend(collection_stories)
            return clean_blocks(result_blocks)

    return clean_blocks(blocks)


def is_paywalled(blocks: list[dict[str, Any]]) -> bool:
    """Detects whether extracted blocks indicate a paywall barrier or truncated preview."""
    all_text = " ".join(b.get("x", "") for b in blocks).lower()
    for phrase in PAYWALL_PHRASES:
        if phrase in all_text:
            return True
    return False


def count_words(blocks: list[dict[str, Any]]) -> int:
    """Calculates total word count across text blocks."""
    words = 0
    for b in blocks:
        if b.get("t") == "story_card":
            words += len((b.get("title") or "").split())
            if b.get("summary"):
                words += len(b["summary"].split())
        elif "x" in b:
            words += len(b["x"].split())
        elif "items" in b:
            for it in b["items"]:
                words += len(it.split())
    return words


def fetch_article_text(article_id: int, force: bool = False) -> None:
    """Executes the fetch ladder (HTTP -> AMP -> Browser) to extract full text for an article."""
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if not article:
            return
        if article.text_status == "ok" and not force:
            return

        article.text_status = "running"
        db.commit()

        url = article.url
        amp_url = article.amp_url
        source = db.get(Source, article.source_id) if article.source_id else None
        preferred_method = source.text_method if source else "auto"
        custom_selector = source.text_selector if source else None
        block_ads = bool(source.text_block_ads) if source else True

    blocks: list[dict[str, Any]] = []
    method_used: Optional[str] = None
    error_msg: Optional[str] = None
    pages_count = 1

    try:
        # Step 1: Force Browser if configured
        if preferred_method == "browser":
            from app.services.browser import fetch_page_content
            html_text = fetch_page_content(url, block_ads=block_ads)
            blocks = to_blocks_from_html(html_text, custom_selector=custom_selector, page_url=url)
            method_used = "browser"

        else:
            # Step 2: Try HTTP fetch
            try:
                res = safe_fetch(url, max_bytes=5 * 1024 * 1024)
                blocks = to_blocks_from_html(res.text, custom_selector=custom_selector, page_url=url)
                method_used = "http"
            except Exception as e:
                logger.debug(f"HTTP fetch failed for {url}: {e}")

            # Step 3: Try AMP if HTTP yielded poor or truncated text
            if (not blocks or count_words(blocks) < 150) and amp_url:
                try:
                    amp_res = safe_fetch(amp_url, max_bytes=5 * 1024 * 1024)
                    amp_blocks = to_blocks_from_html(amp_res.text, page_url=url)
                    if count_words(amp_blocks) > count_words(blocks):
                        blocks = amp_blocks
                        method_used = "amp"
                except Exception:
                    pass

            # Step 4: Fall back to Browser if still sparse or failed
            if not blocks or count_words(blocks) < 150:
                try:
                    from app.services.browser import fetch_page_content
                    browser_html = fetch_page_content(url, block_ads=block_ads)
                    browser_blocks = to_blocks_from_html(browser_html, custom_selector=custom_selector, page_url=url)
                    if count_words(browser_blocks) > count_words(blocks):
                        blocks = browser_blocks
                        method_used = "browser"
                except Exception as e:
                    logger.debug(f"Browser fallback failed for {url}: {e}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed full-text fetch for article {article_id}: {e}", exc_info=True)

    # Status classification
    words = count_words(blocks)
    paywall = is_paywalled(blocks)

    if error_msg and not blocks:
        final_status = "failed"
    elif paywall or (words < 100 and blocks):
        final_status = "partial"
    elif words >= 100:
        final_status = "ok"
    else:
        final_status = "failed"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        art = db.get(Article, article_id)
        if art:
            art.text_blocks_raw = json.dumps(blocks) if blocks else None
            art.text_status = final_status
            art.text_method = method_used
            art.word_count = words
            art.text_pages = pages_count
            art.text_error = error_msg[:500] if error_msg else None
            art.text_fetched_at = now
            db.commit()


job_queue.register("fulltext", fetch_article_text)
