import pytest
from app.database import SessionLocal
from app.models.news import Article, Category, Source


def test_list_and_seed_categories(make_user):
    client, user = make_user("newsreader1")

    res = client.get("/categories")
    assert res.status_code == 200, res.text
    cats = res.json()
    assert len(cats) >= 12
    keys = [c["key"] for c in cats]
    assert "top-stories" in keys
    assert "tech" in keys
    assert "general" in keys


def test_category_create_update_delete(make_user):
    client, user = make_user("newsreader2")

    # Create category
    res = client.post(
        "/categories",
        json={
            "label": "Custom AI",
            "icon": "cpu",
            "keywords": ["llm", "claude", "gemini"],
            "sort_order": 5,
        },
    )
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["label"] == "Custom AI"
    assert created["key"] == "custom-ai"
    assert created["keywords"] == ["llm", "claude", "gemini"]
    cat_id = created["id"]

    # Update category
    res = client.patch(
        f"/categories/{cat_id}",
        json={"label": "AI & ML", "sort_order": 1},
    )
    assert res.status_code == 200, res.text
    updated = res.json()
    assert updated["label"] == "AI & ML"
    assert updated["sort_order"] == 1

    # Delete category
    res = client.delete(f"/categories/{cat_id}")
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == cat_id


def test_general_category_cannot_be_deleted(make_user):
    client, user = make_user("newsreader3")

    res = client.get("/categories")
    cats = res.json()
    general = next(c for c in cats if c["key"] == "general")

    res = client.delete(f"/categories/{general['id']}")
    assert res.status_code == 400
    assert "protected" in res.json()["detail"].lower()


def test_delete_category_reassigns_articles_to_general(make_user):
    client, user = make_user("newsreader4")

    # Create custom category
    res = client.post("/categories", json={"label": "Temporary"})
    cat_id = res.json()["id"]

    # Insert a source and article directly in this category
    with SessionLocal() as db:
        general = db.query(Category).filter_by(household_id=user["household_id"], key="general").first()
        general_id = general.id
        source = Source(
            household_id=user["household_id"],
            url="https://example.com",
            name="Example",
            site_host="example.com",
            fetch_mode="rss",
        )
        db.add(source)
        db.flush()

        article = Article(
            household_id=user["household_id"],
            source_id=source.id,
            url="https://example.com/item1",
            canonical_url="https://example.com/item1",
            url_hash="item1-hash",
            story_id="item1-story",
            title="Temp Article",
            category_id=cat_id,
        )
        db.add(article)
        db.commit()
        art_id = article.id

    # Delete custom category
    res = client.delete(f"/categories/{cat_id}")
    assert res.status_code == 200

    with SessionLocal() as db:
        art = db.get(Article, art_id)
        assert art.category_id == general_id


def test_source_crud(make_user):
    client, user = make_user("sourcemaster")

    # Create source
    res = client.post(
        "/sources",
        json={
            "url": "https://news.ycombinator.com",
            "name": "Hacker News",
            "fetch_mode": "rss",
            "feed_url": "https://news.ycombinator.com/rss",
        },
    )
    assert res.status_code == 201, res.text
    src = res.json()
    assert src["name"] == "Hacker News"
    assert src["site_host"] == "news.ycombinator.com"
    src_id = src["id"]

    # Duplicate check (same host + feed_url) returns 409
    res_dup = client.post(
        "/sources",
        json={
            "url": "https://news.ycombinator.com",
            "name": "Hacker News Copy",
            "fetch_mode": "rss",
            "feed_url": "https://news.ycombinator.com/rss",
        },
    )
    assert res_dup.status_code == 409

    # List sources
    res = client.get("/sources")
    assert res.status_code == 200
    sources = res.json()
    assert len(sources) == 1
    assert sources[0]["id"] == src_id

    # Update source
    res = client.patch(f"/sources/{src_id}", json={"name": "HN Daily", "fetch_pages": 3})
    assert res.status_code == 200
    assert res.json()["name"] == "HN Daily"
    assert res.json()["fetch_pages"] == 3

    # Delete source
    res = client.delete(f"/sources/{src_id}")
    assert res.status_code == 200
    assert res.json()["deleted"] == src_id


def test_household_isolation(make_user):
    client_a, user_a = make_user("user_a", "Household A")
    client_b, user_b = make_user("user_b", "Household B")

    # User A creates a source
    res = client_a.post(
        "/sources",
        json={
            "url": "https://theverge.com",
            "name": "The Verge",
            "fetch_mode": "rss",
        },
    )
    assert res.status_code == 201
    source_a_id = res.json()["id"]

    # User B cannot see it, update it, or delete it (returns 404)
    res = client_b.get("/sources")
    assert len(res.json()) == 0

    res = client_b.patch(f"/sources/{source_a_id}", json={"name": "Hacked"})
    assert res.status_code == 404

    res = client_b.delete(f"/sources/{source_a_id}")
    assert res.status_code == 404

    # User A creates a category
    res = client_a.post("/categories", json={"label": "Secret Category"})
    cat_a_id = res.json()["id"]

    # User B cannot patch or delete User A's category
    res = client_b.patch(f"/categories/{cat_a_id}", json={"label": "Hacked Cat"})
    assert res.status_code == 404

    res = client_b.delete(f"/categories/{cat_a_id}")
    assert res.status_code == 404
