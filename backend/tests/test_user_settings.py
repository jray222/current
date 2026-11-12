from app.database import SessionLocal
from app.models.household import Household


def test_crawl_settings_api(make_user):
    client, user = make_user("settings_user")

    # 1. Get default crawl settings
    res = client.get("/settings/crawl")
    assert res.status_code == 200
    data = res.json()
    assert data["crawl_enabled"] is True
    assert data["crawl_time"] == "06:00"
    assert data["crawl_every_hours"] == 24
    assert len(data["times"]) == 1

    # 2. Update crawl settings (change to 4 hours starting at 08:00)
    patch_res = client.patch(
        "/settings/crawl",
        json={
            "crawl_time": "08:00",
            "crawl_every_hours": 4,
            "ai_categorize": True,
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["crawl_time"] == "08:00"
    assert updated["crawl_every_hours"] == 4
    assert updated["ai_categorize"] is True
    assert len(updated["times"]) == 6


def test_learning_settings_api(make_user):
    client, user = make_user("learning_settings_user")

    # 1. Get learning settings
    res = client.get("/settings/learning")
    assert res.status_code == 200
    data = res.json()
    assert data["n_votes"] == 0
    assert data["muted_terms"] == []

    # 2. Mute a term
    mute_res = client.post("/settings/learning/mute", json={"term": "celebrity"})
    assert mute_res.status_code == 200
    assert "celebrity" in mute_res.json()["muted_terms"]

    # 3. Unmute term
    unmute_res = client.delete("/settings/learning/mute/celebrity")
    assert unmute_res.status_code == 200
    assert "celebrity" not in unmute_res.json()["muted_terms"]

    # 4. Reset model
    reset_res = client.post("/settings/learning/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["n_votes"] == 0


def test_feed_settings_api(make_user):
    client, user = make_user("feed_prefs_user")

    # 1. Get default feed settings
    res = client.get("/api/v1/settings/feed")
    assert res.status_code == 200
    data = res.json()
    assert data["category_order"] == []
    assert data["excluded_categories"] == []
    assert data["preview_lines"] == 2

    # 2. Update feed settings
    patch_res = client.patch(
        "/api/v1/settings/feed",
        json={
            "category_order": ["tech", "world"],
            "excluded_categories": ["sports"],
            "preview_lines": 3,
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["category_order"] == ["tech", "world"]
    assert updated["excluded_categories"] == ["sports"]
    assert updated["preview_lines"] == 3

    # 3. Read back
    res2 = client.get("/api/v1/settings/feed")
    assert res2.status_code == 200
    assert res2.json()["preview_lines"] == 3
    assert res2.json()["excluded_categories"] == ["sports"]

