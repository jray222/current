import json
from unittest.mock import patch
from app.database import SessionLocal
from app.models.news import Article, Source
from app.services.fulltext import (
    clean_blocks,
    to_blocks_from_html,
    is_paywalled,
    fetch_article_text,
)
from app.services.safe_fetch import FetchResponse

SAMPLE_ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Space Exploration</title></head>
<body>
  <article>
    <h2>Deep Space Telescope Unveils New Exoplanet Atmosphere</h2>
    <p>Astronomers today announced observations of water vapor in the atmosphere of a habitable-zone planet.</p>
    <p>The telescope employed transmission spectroscopy during transit events over the past twelve months.</p>
    <blockquote>This is our clearest signal yet of atmospheric complexity outside the solar system.</blockquote>
    <p>Follow us on Twitter for more updates.</p>
    <p>Follow us on Twitter for more updates.</p>
  </article>
</body>
</html>
"""

PAYWALLED_HTML = """<!DOCTYPE html>
<html>
<body>
  <article>
    <h2>Exclusive Financial Analysis</h2>
    <p>Markets rose sharply on morning trading before settling lower.</p>
    <p>Subscribe to continue reading this exclusive report.</p>
  </article>
</body>
</html>
"""


def test_clean_blocks():
    raw_blocks = [
        {"t": "p", "x": "Valid paragraph one with good content."},
        {"t": "p", "x": ""},  # Empty
        {"t": "p", "x": "Sign up for our newsletter to get updates."},  # Boilerplate
        {"t": "p", "x": "Valid paragraph one with good content."},  # Duplicate
        {"t": "p", "x": "Valid paragraph two."},
    ]
    cleaned = clean_blocks(raw_blocks)
    assert len(cleaned) == 2
    assert cleaned[0]["x"] == "Valid paragraph one with good content."
    assert cleaned[1]["x"] == "Valid paragraph two."


def test_to_blocks_from_html():
    blocks = to_blocks_from_html(SAMPLE_ARTICLE_HTML)
    assert len(blocks) >= 3
    types = [b["t"] for b in blocks]
    assert "h2" in types
    assert "p" in types
    assert "blockquote" in types
    # Boilerplate "Follow us on Twitter" and duplicates must be stripped
    for b in blocks:
        assert "Twitter" not in b.get("x", "")


def test_is_paywalled():
    blocks_normal = to_blocks_from_html(SAMPLE_ARTICLE_HTML)
    assert not is_paywalled(blocks_normal)

    blocks_paywall = to_blocks_from_html(PAYWALLED_HTML)
    assert is_paywalled(blocks_paywall)


def test_fetch_article_text_ladder(make_user, monkeypatch):
    client, user = make_user("reader_user")

    def mock_safe_fetch(url, **kwargs):
        return FetchResponse(
            url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            content=SAMPLE_ARTICLE_HTML.encode("utf-8"),
            text=SAMPLE_ARTICLE_HTML,
        )

    from app.services import fulltext
    monkeypatch.setattr(fulltext, "safe_fetch", mock_safe_fetch)

    with SessionLocal() as db:
        src = Source(
            household_id=user["household_id"],
            url="https://astro.example.com",
            name="Astro Daily",
            site_host="astro.example.com",
            fetch_mode="rss",
        )
        db.add(src)
        db.flush()

        art = Article(
            household_id=user["household_id"],
            source_id=src.id,
            url="https://astro.example.com/exoplanet",
            canonical_url="https://astro.example.com/exoplanet",
            url_hash="hash-astro",
            story_id="story-astro",
            title="Deep Space Telescope Unveils Atmosphere",
            text_status="none",
        )
        db.add(art)
        db.commit()
        art_id = art.id

    # Execute text extraction
    fetch_article_text(art_id)

    with SessionLocal() as db:
        article = db.get(Article, art_id)
        assert article.text_status in ("ok", "partial")
        assert article.text_blocks is not None
        assert len(article.text_blocks) >= 3
        assert article.word_count > 20


def test_articles_api(make_user, monkeypatch):
    client_a, user_a = make_user("article_reader_a", "Household Alpha")
    client_b, user_b = make_user("article_reader_b", "Household Beta")

    def mock_safe_fetch(url, **kwargs):
        return FetchResponse(
            url=url,
            status_code=200,
            headers={"content-type": "text/html"},
            content=SAMPLE_ARTICLE_HTML.encode("utf-8"),
            text=SAMPLE_ARTICLE_HTML,
        )

    from app.services import fulltext
    monkeypatch.setattr(fulltext, "safe_fetch", mock_safe_fetch)

    with SessionLocal() as db:
        src = Source(
            household_id=user_a["household_id"],
            url="https://news.example.com",
            name="News",
            site_host="news.example.com",
        )
        db.add(src)
        db.flush()

        art = Article(
            household_id=user_a["household_id"],
            source_id=src.id,
            url="https://news.example.com/article1",
            canonical_url="https://news.example.com/article1",
            url_hash="art1-hash",
            story_id="story-1",
            title="Discovery Article",
            text_status="none",
        )
        db.add(art)
        db.commit()
        art_id = art.id

    # User A gets article
    res = client_a.get(f"/articles/{art_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Discovery Article"
    assert data["text_status"] == "none"

    # User A requests on-demand text
    res = client_a.post(f"/articles/{art_id}/fetch-text?sync=true")
    assert res.status_code == 200
    data = res.json()
    assert data["text_status"] in ("ok", "partial")
    assert data["text_blocks"] is not None

    # User B cannot access User A's article (household isolation 404)
    res_b = client_b.get(f"/articles/{art_id}")
    assert res_b.status_code == 404

    res_b_fetch = client_b.post(f"/articles/{art_id}/fetch-text")
    assert res_b_fetch.status_code == 404
