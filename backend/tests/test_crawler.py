from datetime import datetime, timezone
from unittest.mock import patch
from app.database import SessionLocal
from app.models.news import Article, Category, CrawlRun, Source
from app.services import crawler
from app.services import job_queue
from app.services.feeds import FeedEntry


def test_crawl_source_rss(make_user, monkeypatch):
    client, user = make_user("crawler_user")

    # Mock feedparser results so test makes zero real outbound network calls
    mock_entries = [
        FeedEntry(
            title="Tech Giants Announce Open Source Frontier Model",
            url="https://technews.example.com/item-1",
            summary="A coalition of labs released weights today.",
            author="Staff Writer",
            published_at=datetime(2026, 11, 10, 12, 0, 0),
            image_remote_url="https://technews.example.com/img1.jpg",
            tags=["AI", "Tech"],
        ),
        FeedEntry(
            title="Global Markets Rally After Favorable Jobs Report",
            url="https://technews.example.com/item-2",
            summary="Indices gained 2 percent across the board.",
            author="Jane Doe",
            published_at=datetime(2026, 11, 10, 13, 0, 0),
            image_remote_url=None,
            tags=["Finance"],
        ),
    ]

    def mock_fetch_and_parse(url, **kwargs):
        return {"title": "Tech News Daily"}, mock_entries, url

    monkeypatch.setattr(crawler, "fetch_and_parse_feed", mock_fetch_and_parse)

    with SessionLocal() as db:
        src = Source(
            household_id=user["household_id"],
            url="https://technews.example.com",
            name="Tech News",
            site_host="technews.example.com",
            fetch_mode="rss",
            feed_url="https://technews.example.com/rss",
        )
        db.add(src)
        db.commit()
        source_id = src.id

    # 1. Run crawl
    crawler.crawl_source(source_id, trigger="manual")

    with SessionLocal() as db:
        src = db.get(Source, source_id)
        assert src.crawl_status == "idle"
        assert src.last_new_count == 2
        assert src.fail_streak == 0

        articles = db.query(Article).filter_by(source_id=source_id).all()
        assert len(articles) == 2
        titles = [a.title for a in articles]
        assert "Tech Giants Announce Open Source Frontier Model" in titles

        runs = db.query(CrawlRun).filter_by(source_id=source_id).all()
        assert len(runs) == 1
        assert runs[0].status == "ok"
        assert runs[0].new == 2
        assert runs[0].found == 2

    # 2. Re-crawl should deduplicate and insert 0 new articles
    crawler.crawl_source(source_id, trigger="manual")

    with SessionLocal() as db:
        src = db.get(Source, source_id)
        assert src.last_new_count == 0
        articles = db.query(Article).filter_by(source_id=source_id).all()
        assert len(articles) == 2  # No duplicates


def test_crawl_source_error_handling(make_user, monkeypatch):
    client, user = make_user("crawler_err_user")

    def mock_fetch_fail(url, **kwargs):
        raise ConnectionError("Host unreachable")

    monkeypatch.setattr(crawler, "fetch_and_parse_feed", mock_fetch_fail)

    with SessionLocal() as db:
        src = Source(
            household_id=user["household_id"],
            url="https://broken.example.com",
            name="Broken Source",
            site_host="broken.example.com",
            fetch_mode="rss",
        )
        db.add(src)
        db.commit()
        source_id = src.id

    crawler.crawl_source(source_id, trigger="manual")

    with SessionLocal() as db:
        src = db.get(Source, source_id)
        assert src.crawl_status == "error"
        assert src.fail_streak == 1
        assert "unreachable" in src.last_error

        run = db.query(CrawlRun).filter_by(source_id=source_id).first()
        assert run.status == "failed"
        assert "unreachable" in run.message


def test_resume_pending_crawls(make_user):
    client, user = make_user("crawler_resume_user")

    with SessionLocal() as db:
        src1 = Source(
            household_id=user["household_id"],
            url="https://site1.com",
            name="Site 1",
            site_host="site1.com",
            crawl_status="running",
        )
        src2 = Source(
            household_id=user["household_id"],
            url="https://site2.com",
            name="Site 2",
            site_host="site2.com",
            crawl_status="queued",
        )
        run = CrawlRun(
            household_id=user["household_id"],
            source_id=1,
            trigger="manual",
            status="running",
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add_all([src1, src2, run])
        db.commit()

        crawler.resume_pending_crawls(db)

        assert src1.crawl_status == "idle"
        assert src2.crawl_status == "idle"
        assert run.status == "aborted"
