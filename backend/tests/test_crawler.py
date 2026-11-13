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


def test_cross_household_crawl_shares_scrape(make_user, monkeypatch):
    _, user_a = make_user("shared_crawl_a", "Household A")
    _, user_b = make_user("shared_crawl_b", "Household B")

    fetch_calls = 0
    mock_entries = [
        FeedEntry(
            title="Shared Site Headline",
            url="https://shared.example.com/story-1",
            summary="Shared summary.",
            author="Reporter",
            published_at=datetime(2026, 11, 10, 12, 0, 0),
            image_remote_url=None,
            tags=["World"],
        )
    ]

    def mock_fetch_and_parse(url, **kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
        return {"title": "Shared Daily"}, mock_entries, url

    monkeypatch.setattr(crawler, "fetch_and_parse_feed", mock_fetch_and_parse)

    with SessionLocal() as db:
        src_a = Source(
            household_id=user_a["household_id"],
            url="https://shared.example.com",
            name="Shared Daily",
            site_host="shared.example.com",
            fetch_mode="rss",
            feed_url="https://shared.example.com/rss",
        )
        src_b = Source(
            household_id=user_b["household_id"],
            url="https://shared.example.com",
            name="Shared Daily",
            site_host="shared.example.com",
            fetch_mode="rss",
            feed_url="https://shared.example.com/rss",
        )
        db.add_all([src_a, src_b])
        db.commit()
        src_a_id, src_b_id = src_a.id, src_b.id

    crawler.crawl_source(src_a_id, trigger="schedule")
    assert fetch_calls == 1

    # Second household crawling the same feed reuses the cached scrape without hitting the network
    crawler.crawl_source(src_b_id, trigger="schedule")
    assert fetch_calls == 1

    with SessionLocal() as db:
        arts_a = db.query(Article).filter_by(household_id=user_a["household_id"]).all()
        arts_b = db.query(Article).filter_by(household_id=user_b["household_id"]).all()
        assert len(arts_a) == 1
        assert len(arts_b) == 1
        assert arts_a[0].id != arts_b[0].id
        assert arts_b[0].title == "Shared Site Headline"

    # Explicit force=True bypasses the shared cache
    crawler.crawl_source(src_b_id, trigger="manual", force=True)
    assert fetch_calls == 2
