"""Data retention cleaner: purges stale unvoted articles, skipped articles,
and old crawl run logs while permanently preserving kept reading list items.
"""
from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.news import Article, CrawlRun, Vote
from app.services.images import delete_image

logger = logging.getLogger("current.prune")

RETENTION_DAYS_UNVOTED = 30
RETENTION_DAYS_SKIPPED = 14
RETENTION_DAYS_RUNS = 30


def prune_retention(db: Session) -> dict[str, int]:
    """Runs retention cleanup across articles, images, and crawl run logs."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff_unvoted = now - timedelta(days=RETENTION_DAYS_UNVOTED)
    cutoff_skipped = now - timedelta(days=RETENTION_DAYS_SKIPPED)
    cutoff_runs = now - timedelta(days=RETENTION_DAYS_RUNS)

    # 1. Collect articles with a 'keep' vote (permanently protected)
    kept_article_ids = (
        db.query(Vote.article_id)
        .filter(Vote.verdict == "keep", Vote.article_id.isnot(None))
        .scalar_subquery()
    )

    # 2. Collect articles with a 'skip' vote older than 14 days
    skipped_old_ids = (
        db.query(Vote.article_id)
        .filter(
            Vote.verdict == "skip",
            Vote.created_at < cutoff_skipped,
            Vote.article_id.isnot(None),
        )
        .scalar_subquery()
    )

    # 3. Collect unvoted articles older than 30 days
    any_voted_ids = (
        db.query(Vote.article_id)
        .filter(Vote.article_id.isnot(None))
        .scalar_subquery()
    )

    # Find candidates to delete
    to_delete = (
        db.query(Article)
        .filter(
            ~Article.id.in_(kept_article_ids),
            (
                Article.id.in_(skipped_old_ids)
                | (
                    ~Article.id.in_(any_voted_ids)
                    & (Article.discovered_at < cutoff_unvoted)
                )
            ),
        )
        .limit(500)
        .all()
    )

    articles_pruned = len(to_delete)
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

    # 4. Prune completed crawl runs older than 30 days
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
