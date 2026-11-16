"""Data retention cleaner: purges stale articles older than retention window
and old crawl run logs while permanently preserving kept reading list items.
"""
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models.news import Article, CrawlRun, Vote
from app.services.images import delete_image

logger = logging.getLogger("current.prune")

RETENTION_DAYS_RUNS = 30
_BATCH_SIZE = 500


def retention_days() -> int:
    """Returns configured article retention window in days (minimum 1)."""
    return max(1, int(settings.RETENTION_DAYS or 1))


def fresh_article_cutoff(now: Optional[datetime] = None) -> datetime:
    """Returns the naive UTC cutoff timestamp for fresh (non-stale) articles."""
    ref = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return ref - timedelta(days=retention_days())


def fresh_article_clause(now: Optional[datetime] = None):
    """SQLAlchemy filter expression matching articles within the freshness window."""
    cutoff = fresh_article_cutoff(now)
    return (
        (func.coalesce(Article.published_at, Article.discovered_at) >= cutoff)
        & (Article.discovered_at >= cutoff)
    )


def prune_retention(db: Session) -> dict[str, int]:
    """Runs retention cleanup across articles, images, and crawl run logs."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff_articles = now - timedelta(days=retention_days())
    cutoff_runs = now - timedelta(days=RETENTION_DAYS_RUNS)

    # 1. Collect articles with an active 'keep' vote (permanently protected)
    kept_article_ids = (
        db.query(Vote.article_id)
        .filter(
            Vote.verdict == "keep",
            Vote.kept_state != "removed",
            Vote.article_id.isnot(None),
        )
        .scalar_subquery()
    )

    # 2. Delete all non-kept articles older than the retention window (by published_at or discovered_at)
    articles_pruned = 0
    while True:
        to_delete = (
            db.query(Article)
            .filter(
                ~Article.id.in_(kept_article_ids),
                (
                    (func.coalesce(Article.published_at, Article.discovered_at) < cutoff_articles)
                    | (Article.discovered_at < cutoff_articles)
                ),
            )
            .limit(_BATCH_SIZE)
            .all()
        )
        if not to_delete:
            break

        for art in to_delete:
            if art.thumb_path:
                # Only unlink from disk if no other article references this thumbnail
                other_ref = (
                    db.query(Article.id)
                    .filter(Article.thumb_path == art.thumb_path, Article.id != art.id)
                    .first()
                )
                if not other_ref:
                    delete_image(art.thumb_path)
            db.delete(art)

        db.commit()
        articles_pruned += len(to_delete)
        if len(to_delete) < _BATCH_SIZE:
            break

    # 3. Prune completed crawl runs older than 30 days
    runs_deleted = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.status != "running",
            CrawlRun.started_at < cutoff_runs,
        )
        .delete(synchronize_session=False)
    )

    db.commit()

    logger.info(
        f"Pruned {articles_pruned} stale articles and {runs_deleted} old crawl runs."
    )
    return {
        "pruned_articles": articles_pruned,
        "pruned_crawl_runs": runs_deleted,
    }
