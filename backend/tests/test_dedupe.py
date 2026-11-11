from datetime import datetime, timezone, timedelta
from app.database import SessionLocal
from app.models.news import Article, Source
from app.services.dedupe import (
    canonical_url,
    url_hash,
    tokenize_title,
    jaccard_similarity,
    find_or_create_story_id,
)


def test_canonical_url_stripping():
    # Strips utm params, fbclid, fragments, lowers host, normalizes trailing slash
    raw = "https://WWW.Example.com:443/Tech/Article/?utm_source=twitter&fbclid=12345#heading"
    clean = canonical_url(raw)
    assert clean == "https://www.example.com/Tech/Article"

    # Preserves legitimate query parameters and sorts them
    raw2 = "http://example.com/search?q=news&page=2&utm_medium=email"
    clean2 = canonical_url(raw2)
    assert clean2 == "http://example.com/search?page=2&q=news"

    # Empty string handling
    assert canonical_url("") == ""


def test_url_hash():
    h1 = url_hash("https://example.com/story?utm_source=newsletter")
    h2 = url_hash("https://example.com/story")
    assert h1 == h2
    assert len(h1) == 64


def test_tokenize_title_and_jaccard():
    t1 = "Breaking: Tech Stocks Surge on Strong AI Earnings"
    t2 = "Tech Stocks Surge Today Following Strong AI Earnings Report"
    t3 = "Global Climate Summit Concludes With New Agreement"

    tokens1 = tokenize_title(t1)
    tokens2 = tokenize_title(t2)
    tokens3 = tokenize_title(t3)

    assert "breaking" in tokens1
    assert "stocks" in tokens1
    assert "on" not in tokens1  # Stopword removed

    sim12 = jaccard_similarity(tokens1, tokens2)
    assert sim12 >= 0.5  # High similarity on shared tokens

    sim13 = jaccard_similarity(tokens1, tokens3)
    assert sim13 < 0.1   # Unrelated stories


def test_find_or_create_story_id(make_user):
    client, user = make_user("dedupe_user")

    with SessionLocal() as db:
        source = Source(
            household_id=user["household_id"],
            url="https://site.com",
            name="Site",
            site_host="site.com",
            fetch_mode="rss",
        )
        db.add(source)
        db.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        art1 = Article(
            household_id=user["household_id"],
            source_id=source.id,
            url="https://site.com/art1",
            canonical_url="https://site.com/art1",
            url_hash="h1",
            story_id="story-abc-123",
            title="Federal Reserve Cuts Interest Rates by Half Point",
            discovered_at=now,
        )
        db.add(art1)
        db.commit()

        # Similar article from another outlet within the 48h window should cluster into the same story_id
        similar_title = "Fed Cuts Key Interest Rates by Half a Point"
        matched_story = find_or_create_story_id(
            db,
            user["household_id"],
            similar_title,
            reference_time=now,
            threshold=0.5,
        )
        assert matched_story == "story-abc-123"

        # Completely different story gets a new story_id
        different_title = "NASA Space Telescope Discovers Distant Habitable Exoplanet"
        new_story = find_or_create_story_id(
            db,
            user["household_id"],
            different_title,
            reference_time=now,
            threshold=0.5,
        )
        assert new_story != "story-abc-123"
        assert len(new_story) >= 12
