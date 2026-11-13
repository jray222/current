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


def test_collection_blocks_extraction():
    collection_html = """<!DOCTYPE html>
    <html><body><main>
      <h1>Beyond the Headlines: Curated stories</h1>
      <div class="PagePromo">
        <h2 class="PagePromo-title"><a href="https://apnews.com/article/sub-story-1">First Major Investigative Story in This Curated Roundup</a></h2>
        <div class="PagePromo-description">Teaser description for story one with enough details.</div>
      </div>
      <div class="PagePromo">
        <h2 class="PagePromo-title"><a href="https://apnews.com/article/sub-story-2">Second In-Depth Dispatch From Regional Correspondents</a></h2>
        <div class="PagePromo-description">Teaser description for story two with enough details.</div>
      </div>
      <div class="PagePromo">
        <h2 class="PagePromo-title"><a href="https://apnews.com/article/sub-story-3">Third Feature Article Covering Cultural Phenomena Worldwide</a></h2>
        <div class="PagePromo-description">Teaser description for story three with enough details.</div>
      </div>
    </main></body></html>
    """
    blocks = to_blocks_from_html(collection_html, page_url="https://apnews.com/hub/beyond-the-headlines")
    assert len(blocks) >= 3
    types = [b["t"] for b in blocks]
    assert "collection_header" in types
    story_cards = [b for b in blocks if b["t"] == "story_card"]
    assert len(story_cards) == 3
    assert "First Major Investigative Story" in story_cards[0]["title"]
    assert story_cards[0]["url"] == "https://apnews.com/article/sub-story-1"
    assert "Teaser description for story one" in story_cards[0]["summary"]


def test_cross_household_fulltext_reuse(make_user, monkeypatch):
    client_a, user_a = make_user("ft_shared_a", "Household FT A")
    client_b, user_b = make_user("ft_shared_b", "Household FT B")

    fetch_calls = 0

    def mock_safe_fetch(url, **kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
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
        src_a = Source(
            household_id=user_a["household_id"],
            url="https://sharedft.example.com",
            name="Shared FT",
            site_host="sharedft.example.com",
        )
        src_b = Source(
            household_id=user_b["household_id"],
            url="https://sharedft.example.com",
            name="Shared FT",
            site_host="sharedft.example.com",
        )
        db.add_all([src_a, src_b])
        db.flush()

        art_a = Article(
            household_id=user_a["household_id"],
            source_id=src_a.id,
            url="https://sharedft.example.com/story",
            canonical_url="https://sharedft.example.com/story",
            url_hash="shared-ft-hash",
            story_id="s-ft-a",
            title="Shared Story",
            text_status="none",
        )
        art_b = Article(
            household_id=user_b["household_id"],
            source_id=src_b.id,
            url="https://sharedft.example.com/story",
            canonical_url="https://sharedft.example.com/story",
            url_hash="shared-ft-hash",
            story_id="s-ft-b",
            title="Shared Story",
            text_status="none",
        )
        db.add_all([art_a, art_b])
        db.commit()
        art_a_id, art_b_id = art_a.id, art_b.id

    fetch_article_text(art_a_id)
    assert fetch_calls == 1

    # Household B gets the extracted blocks without a second outbound fetch
    fetch_article_text(art_b_id)
    assert fetch_calls == 1

    with SessionLocal() as db:
        b = db.get(Article, art_b_id)
        assert b.text_status in ("ok", "partial")
        assert b.text_blocks is not None
        assert b.word_count > 20

    # Household isolation remains enforced
    assert client_b.get(f"/articles/{art_a_id}").status_code == 404


