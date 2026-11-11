"""Core crawler engine: source probing, RSS/HTML/browser crawling, article ingestion,
story clustering, and background job handling.
"""
from datetime import datetime, timezone
import logging
import traceback
import urllib.parse
from typing import Optional, Any
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.news import Article, Category, CrawlRun, Source
from app.services import categories as category_service
from app.services import job_queue
from app.services.adblock import is_ad_host
from app.services.dedupe import canonical_url, find_or_create_story_id, url_hash
from app.services.feeds import FeedEntry, fetch_and_parse_feed
from app.services.job_queue import Priority
from app.services.pages import extract_article_links, extract_meta
from app.services.safe_fetch import safe_fetch

logger = logging.getLogger("current.crawler")
MAX_NEW_PER_SOURCE = 50


def check_source(db: Session, household_id: int, url: str) -> dict[str, Any]:
    """Probes a URL across RSS -> HTML -> Browser to detect feed existence,
    article links, and recommended fetch mode.
    """
    clean_target = url.strip()
    parsed = urllib.parse.urlparse(clean_target)
    site_host = parsed.netloc.lower()

    # 1. Probe RSS / Atom feed
    try:
        info, entries, final_url = fetch_and_parse_feed(clean_target)
        if entries:
            sample_titles = [e.title for e in entries[:5]]
            return {
                "mode": "rss",
                "name": info.get("title") or site_host,
                "feed_url": final_url,
                "listing_url": None,
                "found_count": len(entries),
                "sample_titles": sample_titles,
                "site_host": site_host,
            }
    except Exception:
        pass

    # 2. Probe standard HTML listing
    try:
        res = safe_fetch(clean_target, max_bytes=2 * 1024 * 1024)
        links = extract_article_links(res.text, res.url)
        if len(links) >= 2:
            return {
                "mode": "html",
                "name": site_host,
                "feed_url": None,
                "listing_url": res.url,
                "found_count": len(links),
                "sample_titles": links[:5],
                "site_host": site_host,
            }
    except Exception:
        pass

    # 3. Probe with Headless Browser for JS-rendered websites
    try:
        from app.services.browser import fetch_page_content
        html_content = fetch_page_content(clean_target, timeout_ms=15000)
        browser_links = extract_article_links(html_content, clean_target)
        if browser_links:
            return {
                "mode": "browser",
                "name": site_host,
                "feed_url": None,
                "listing_url": clean_target,
                "found_count": len(browser_links),
                "sample_titles": browser_links[:5],
                "site_host": site_host,
            }
    except Exception:
        pass

    return {
        "mode": "rss",
        "name": site_host,
        "feed_url": clean_target,
        "listing_url": None,
        "found_count": 0,
        "sample_titles": [],
        "site_host": site_host,
    }


def _ingest_entries(
    db: Session,
    source: Source,
    entries: list[FeedEntry],
) -> tuple[int, int]:
    """Ingests discovered feed entries into the articles table with deduplication
    and story clustering. Returns (found_count, new_count).
    """
    found_count = len(entries)
    new_count = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    household_cats = (
        db.query(Category)
        .filter(Category.household_id == source.household_id)
        .all()
    )
    general_cat = next((c for c in household_cats if c.key == "general"), None)
    if not general_cat:
        general_cat = category_service.get_general_category(db, source.household_id)
        household_cats.append(general_cat)
    general_id = general_cat.id

    for item in entries[:MAX_NEW_PER_SOURCE]:
        if not item.url or not item.title:
            continue

        c_url = canonical_url(item.url)
        h = url_hash(c_url)

        # Check existing article in household
        exists = (
            db.query(Article.id)
            .filter(Article.household_id == source.household_id, Article.url_hash == h)
            .first()
        )
        if exists:
            continue

        # Story clustering
        story_id = find_or_create_story_id(
            db,
            household_id=source.household_id,
            title=item.title,
            reference_time=item.published_at or now,
        )

        # Category resolution
        if source.category_id:
            category_id = source.category_id
        else:
            category_id = category_service.keyword_categorize(
                title=item.title,
                summary=item.summary,
                feed_tags=item.tags,
                categories=household_cats,
                general_id=general_id,
            )

        article = Article(
            household_id=source.household_id,
            source_id=source.id,
            category_id=category_id,
            url=item.url,
            canonical_url=c_url,
            url_hash=h,
            story_id=story_id,
            title=item.title,
            summary=item.summary,
            author=item.author,
            published_at=item.published_at,
            discovered_at=now,
            image_remote_url=item.image_remote_url,
            lang="en",
            text_status="none",
        )
        article.feed_tags = item.tags
        db.add(article)
        db.flush()
        new_count += 1

        # Background thumb download
        if item.image_remote_url:
            job_queue.enqueue(
                "download_article_image",
                article.id,
                priority=Priority.LOW,
                dedupe_key=f"img-{article.id}",
            )

        # Optional full-text crawl right now
        if source.text_when == "crawl":
            job_queue.enqueue(
                "fulltext",
                article.id,
                priority=Priority.NORMAL,
                dedupe_key=f"text-{article.id}",
            )

    db.commit()
    return found_count, new_count


def crawl_source(source_id: int, trigger: str = "manual", force: bool = False) -> None:
    """Executes a single crawl run for a source, handling RSS, HTML, and browser modes."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with SessionLocal() as db:
        source = db.get(Source, source_id)
        if not source:
            return
        if not source.enabled and not force:
            return

        source.crawl_status = "running"
        run = CrawlRun(
            household_id=source.household_id,
            source_id=source.id,
            trigger=trigger,
            mode_used=source.fetch_mode,
            status="running",
            started_at=now,
            found=0,
            new=0,
            skipped_robots=0,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        run_id = run.id
        fetch_mode = source.fetch_mode
        feed_url = source.feed_url
        listing_url = source.listing_url
        url = source.url
        link_pattern = source.link_pattern
        link_selector = source.link_selector

    # Perform fetching outside the active lock transaction
    error_msg = None
    found_count = 0
    new_count = 0

    try:
        entries: list[FeedEntry] = []

        if fetch_mode == "rss":
            feed_target = feed_url or url
            _info, entries, _final = fetch_and_parse_feed(feed_target)

        elif fetch_mode == "html":
            listing_target = listing_url or url
            res = safe_fetch(listing_target)
            links = extract_article_links(
                res.text,
                res.url,
                link_pattern=link_pattern,
                link_selector=link_selector,
            )
            for link in links[:MAX_NEW_PER_SOURCE]:
                try:
                    art_res = safe_fetch(link, max_bytes=2 * 1024 * 1024)
                    meta = extract_meta(art_res.text, art_res.url)
                    entries.append(
                        FeedEntry(
                            title=meta["title"],
                            url=art_res.url,
                            summary=meta["summary"],
                            author=meta["author"],
                            published_at=meta["published_at"],
                            image_remote_url=meta["image_remote_url"],
                            tags=meta["feed_tags"],
                        )
                    )
                except Exception:
                    continue

        elif fetch_mode == "browser":
            from app.services.browser import fetch_page_content
            listing_target = listing_url or url
            html_text = fetch_page_content(listing_target)
            links = extract_article_links(
                html_text,
                listing_target,
                link_pattern=link_pattern,
                link_selector=link_selector,
            )
            for link in links[:MAX_NEW_PER_SOURCE]:
                try:
                    art_html = fetch_page_content(link)
                    meta = extract_meta(art_html, link)
                    entries.append(
                        FeedEntry(
                            title=meta["title"],
                            url=link,
                            summary=meta["summary"],
                            author=meta["author"],
                            published_at=meta["published_at"],
                            image_remote_url=meta["image_remote_url"],
                            tags=meta["feed_tags"],
                        )
                    )
                except Exception:
                    continue

        with SessionLocal() as db:
            src = db.get(Source, source_id)
            if src:
                found_count, new_count = _ingest_entries(db, src, entries)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error crawling source {source_id}: {e}", exc_info=True)

    # Save final run status
    finish_time = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        src = db.get(Source, source_id)
        run_record = db.get(CrawlRun, run_id)

        if src:
            if error_msg:
                src.crawl_status = "error"
                src.fail_streak += 1
                src.last_error = error_msg[:500]
            else:
                src.crawl_status = "idle"
                src.last_crawl_at = finish_time
                src.last_new_count = new_count
                src.fail_streak = 0
                src.last_error = None

        if run_record:
            if error_msg:
                run_record.status = "failed"
                run_record.message = error_msg[:500]
            else:
                run_record.status = "ok"
                run_record.found = found_count
                run_record.new = new_count
            run_record.finished_at = finish_time

        db.commit()


def enqueue_source_crawl(source_id: int, trigger: str = "manual", priority: int = Priority.NORMAL) -> bool:
    """Enqueues a crawl job for a specific source."""
    with SessionLocal() as db:
        src = db.get(Source, source_id)
        if src:
            src.crawl_status = "queued"
            db.commit()

    return job_queue.enqueue(
        "crawl_source",
        source_id,
        trigger,
        priority=priority,
        dedupe_key=f"crawl-{source_id}",
    )


def crawl_household(household_id: int, trigger: str = "schedule") -> int:
    """Queues crawl jobs for all enabled sources in a household."""
    with SessionLocal() as db:
        sources = (
            db.query(Source.id)
            .filter(Source.household_id == household_id, Source.enabled == 1)
            .all()
        )
        count = 0
        for (sid,) in sources:
            if enqueue_source_crawl(sid, trigger=trigger, priority=Priority.NORMAL):
                count += 1
        return count


def resume_pending_crawls(db: Session) -> None:
    """Resets any stale in-progress statuses on server startup."""
    db.query(Source).filter(Source.crawl_status.in_(["queued", "running"])).update(
        {Source.crawl_status: "idle"}
    )
    db.query(CrawlRun).filter(CrawlRun.status == "running").update(
        {CrawlRun.status: "aborted", CrawlRun.message: "Interrupted by server restart"}
    )
    db.commit()


job_queue.register("crawl_source", crawl_source)
