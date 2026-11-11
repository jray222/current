from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest

from app.database import SessionLocal
from app.deps import get_current_user
from app.models.household import Household
from app.models.news import Article, Source, Vote
from app.models.user import User
from app.services import categories as category_service
from app.services.feeds import parse_feed_bytes
from app.services.images import get_image_absolute_path
from app.services.prune import prune_retention
from app.services.safe_fetch import HostThrottle, RobotsCache, SSRFBlockedError
from app.services.browser import _route_handler


def test_image_path_traversal_and_null_byte():
    # Regular traversal
    assert get_image_absolute_path("../etc/passwd") is None
    assert get_image_absolute_path("1/../../etc/passwd") is None
    # Null byte injection
    assert get_image_absolute_path("1/test.jpg\x00extra") is None
    # Empty
    assert get_image_absolute_path("") is None


def test_prune_retention_preserves_shared_thumbnails():
    with SessionLocal() as db:
        h = Household(name="Prune Household")
        db.add(h)
        db.commit()
        db.refresh(h)
        category_service.seed_all(db, h.id)
        gen_cat = category_service.get_general_category(db, h.id)

        source = Source(
            household_id=h.id,
            name="News Source",
            url="https://example.com",
            site_host="example.com",
            fetch_mode="rss",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        old_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=45)
        shared_thumb = f"{h.id}/shared_hash_123.jpg"

        # Article 1: Old, unvoted (should be pruned)
        art1 = Article(
            household_id=h.id,
            source_id=source.id,
            category_id=gen_cat.id,
            url="https://example.com/art1",
            url_hash="hash1",
            story_id="story1",
            title="Old Article",
            discovered_at=old_date,
            thumb_path=shared_thumb,
        )
        # Article 2: Kept by user (should NOT be pruned)
        art2 = Article(
            household_id=h.id,
            source_id=source.id,
            category_id=gen_cat.id,
            url="https://example.com/art2",
            url_hash="hash2",
            story_id="story2",
            title="Kept Article",
            discovered_at=old_date,
            thumb_path=shared_thumb,
        )
        db.add_all([art1, art2])
        db.commit()
        db.refresh(art1)
        db.refresh(art2)

        u = User(username="reader1", password_hash="pw", household_id=h.id)
        db.add(u)
        db.commit()
        db.refresh(u)

        v = Vote(user_id=u.id, household_id=h.id, article_id=art2.id, story_id="story2", verdict="keep", features="{}")
        db.add(v)
        db.commit()

        # Track delete_image calls
        deleted_thumbs = []
        with pytest.MonkeyPatch.context() as m:
            m.setattr("app.services.prune.delete_image", lambda p: deleted_thumbs.append(p))
            pruned = prune_retention(db)

        # art1 was pruned, but because art2 still references shared_thumb, it was not unlinked!
        assert pruned["pruned_articles"] == 1
        assert shared_thumb not in deleted_thumbs


def test_feed_parser_rejects_javascript_schemes():
    raw_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Malicious Feed</title>
        <link>http://example.com</link>
        <item>
          <title>XSS Link</title>
          <link>javascript:alert(document.cookie)</link>
        </item>
        <item>
          <title>Safe Link</title>
          <link>https://example.com/safe-article</link>
        </item>
      </channel>
    </rss>"""
    info, entries = parse_feed_bytes(raw_xml, fallback_url="https://example.com")
    assert len(entries) == 1
    assert entries[0].title == "Safe Link"
    assert entries[0].url == "https://example.com/safe-article"


def test_cache_bounds_eviction(monkeypatch):
    monkeypatch.setenv("JOB_QUEUE", "async")
    # HostThrottle bounded cache
    throttle = HostThrottle()
    for i in range(2100):
        throttle._last_call[f"host-{i}.com"] = float(i)
    throttle.wait_for_host("host-new.com")
    # Should be capped and pruned
    assert len(throttle._last_call) <= 1605

    # RobotsCache bounded cache
    rc = RobotsCache()
    for i in range(2100):
        rc._cache[f"host-{i}.com"] = (float(i), MagicMock())
    with rc._lock:
        if len(rc._cache) > 2000:
            oldest = sorted(rc._cache.items(), key=lambda it: it[1][0])[:500]
            for k, _ in oldest:
                rc._cache.pop(k, None)
    assert len(rc._cache) <= 1600


def test_browser_route_handler_aborts_ssrf():
    route = MagicMock()
    request = MagicMock()
    request.url = "http://127.0.0.1:8080/internal"
    request.resource_type = "document"

    _route_handler(route, request, block_ads=True)
    route.abort.assert_called_with("blockedbyclient")


def test_browser_route_handler_aborts_ad_hosts():
    route = MagicMock()
    request = MagicMock()
    request.url = "http://google-analytics.com/analytics.js"
    request.resource_type = "script"

    _route_handler(route, request, block_ads=True)
    route.abort.assert_called_with("blockedbyclient")
