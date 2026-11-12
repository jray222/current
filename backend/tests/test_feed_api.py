from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.news import Article, Category, Source, Vote


def _setup_feed_test_data(household_id: int):
    with SessionLocal() as db:
        cat_tech = db.query(Category).filter_by(household_id=household_id, key="tech").first()
        cat_world = db.query(Category).filter_by(household_id=household_id, key="world").first()

        src1 = Source(
            household_id=household_id,
            url="https://source1.example.com",
            name="Source One",
            site_host="source1.example.com",
            category_id=cat_tech.id if cat_tech else None,
        )
        src2 = Source(
            household_id=household_id,
            url="https://source2.example.com",
            name="Source Two",
            site_host="source2.example.com",
            category_id=cat_tech.id if cat_tech else None,
        )
        db.add_all([src1, src2])
        db.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Two articles on the SAME story (story-cluster-1)
        art1 = Article(
            household_id=household_id,
            source_id=src1.id,
            category_id=cat_tech.id if cat_tech else None,
            url="https://source1.example.com/art1",
            canonical_url="https://source1.example.com/art1",
            url_hash="h-art1",
            story_id="story-cluster-1",
            title="Next Gen Semiconductor Fabrication Facility Opens",
            summary="A cutting-edge fab announced production milestones today.",
            discovered_at=now,
        )
        art2 = Article(
            household_id=household_id,
            source_id=src2.id,
            category_id=cat_tech.id if cat_tech else None,
            url="https://source2.example.com/art2",
            canonical_url="https://source2.example.com/art2",
            url_hash="h-art2",
            story_id="story-cluster-1",
            title="Major Fab Facility Achieves Volume Production",
            summary="Secondary coverage of the new semiconductor plant.",
            discovered_at=now,
        )

        # Independent article in World
        art3 = Article(
            household_id=household_id,
            source_id=src1.id,
            category_id=cat_world.id if cat_world else None,
            url="https://source1.example.com/art3",
            canonical_url="https://source1.example.com/art3",
            url_hash="h-art3",
            story_id="story-world-1",
            title="International Climate Summit Reaches Accord",
            summary="Delegates agreed to new conservation initiatives.",
            discovered_at=now,
        )

        db.add_all([art1, art2, art3])
        db.commit()
        return art1.id, art2.id, art3.id


def test_frontpage_and_story_grouping(make_user):
    client, user = make_user("frontpage_user")
    art1_id, art2_id, art3_id = _setup_feed_test_data(user["household_id"])

    res = client.get("/frontpage")
    assert res.status_code == 200
    data = res.json()

    assert data["lead_story"] is not None
    # Sibling article on the same story should be grouped in also_in
    lead = data["lead_story"]
    if lead["story_id"] == "story-cluster-1":
        assert len(lead["also_in"]) == 1
        assert lead["also_in"][0]["source_name"] in ("Source One", "Source Two")


def test_voting_swiping_and_undo(make_user):
    client, user = make_user("swiping_user")
    art1_id, art2_id, art3_id = _setup_feed_test_data(user["household_id"])

    # 1. Vote Keep (swipe right) on art1
    res = client.post("/votes", json={"article_id": art1_id, "verdict": "keep"})
    assert res.status_code == 200
    assert res.json()["verdict"] == "keep"

    # Article 1 is now marked as kept
    res_kept = client.get("/kept")
    assert res_kept.status_code == 200
    kept_items = res_kept.json()
    assert len(kept_items) == 1
    assert kept_items[0]["article"]["id"] == art1_id
    assert kept_items[0]["kept_state"] == "unread"

    # Update kept status to 'read'
    res_patch = client.patch(f"/kept/{art1_id}", json={"kept_state": "read"})
    assert res_patch.status_code == 200

    # 2. Vote Skip (swipe left) on art3
    res_skip = client.post("/votes", json={"article_id": art3_id, "verdict": "skip"})
    assert res_skip.status_code == 200

    # Frontpage should now exclude both voted articles
    res_fp = client.get("/frontpage")
    fp_data = res_fp.json()
    all_fp_ids = []
    if fp_data["lead_story"]:
        all_fp_ids.append(fp_data["lead_story"]["id"])
    for s in fp_data["sections"]:
        all_fp_ids.extend([a["id"] for a in s["articles"]])

    assert art1_id not in all_fp_ids
    assert art3_id not in all_fp_ids

    # 3. Undo vote on art1
    res_undo = client.delete(f"/votes/{art1_id}")
    assert res_undo.status_code == 200

    # After undo, art1 is removed from kept list
    res_kept_after = client.get("/kept")
    assert len(res_kept_after.json()) == 0


def test_feed_household_isolation(make_user):
    client_a, user_a = make_user("user_iso_a", "Household A")
    client_b, user_b = make_user("user_iso_b", "Household B")

    art1_id, _, _ = _setup_feed_test_data(user_a["household_id"])

    # User B cannot see User A's frontpage items
    res_b = client_b.get("/frontpage")
    assert res_b.json()["lead_story"] is None

    # User B cannot vote on User A's article (404)
    res_vote_b = client_b.post("/votes", json={"article_id": art1_id, "verdict": "keep"})
    assert res_vote_b.status_code == 404


def test_feed_opened_status_and_customization(make_user):
    client, user = make_user("feed_ux_user")
    art1_id, art2_id, art3_id = _setup_feed_test_data(user["household_id"])

    # 1. Vote 'open' on art1 - it should NOT be removed from frontpage, but marked is_opened=True
    res_open = client.post("/votes", json={"article_id": art1_id, "verdict": "open"})
    assert res_open.status_code == 200

    res_fp = client.get("/api/v1/frontpage")
    assert res_fp.status_code == 200
    fp_data = res_fp.json()

    # Find art1 in frontpage
    items = []
    if fp_data["lead_story"]:
        items.append(fp_data["lead_story"])
    for sec in fp_data["sections"]:
        items.extend(sec["articles"])

    matching = [a for a in items if a["id"] == art1_id]
    assert len(matching) == 1
    assert matching[0]["is_opened"] is True

    # 2. Exclude category 'world' via feed settings
    client.patch("/api/v1/settings/feed", json={"excluded_categories": ["world"]})
    res_fp2 = client.get("/api/v1/frontpage")
    section_keys = [s["category"]["key"] for s in res_fp2.json()["sections"]]
    assert "world" not in section_keys


def test_articles_open_by_url(make_user, monkeypatch):
    client, user = make_user("open_by_url_user")

    # Mock fetch_article_text so it doesn't do network calls in tests
    from app.services import fulltext
    def mock_fetch(url, block_ads=True):
        return {
            "title": "Ingested Mock Story",
            "byline": "Reporter",
            "published_at": None,
            "lead_image_url": None,
            "blocks": [{"type": "paragraph", "text": "This is ingested full text."}],
            "word_count": 6,
            "status": "ok",
        }
    monkeypatch.setattr(fulltext, "fetch_article_text", mock_fetch)

    # Ingest a new URL
    res = client.post(
        "/api/v1/articles/open-by-url",
        json={"url": "https://example.com/breaking-news-story", "title": "Ingested Mock Story"},
    )
    assert res.status_code == 200
    article_id = res.json()["id"]

    # Calling again with same URL returns existing id
    res2 = client.post(
        "/api/v1/articles/open-by-url",
        json={"url": "https://example.com/breaking-news-story"},
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == article_id

