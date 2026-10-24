"""Decks, collection, pictures and progress. No network: sources are faked or served by httpx.MockTransport."""
import io
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from PIL import Image

from app.database import SessionLocal
from app.models import Card, CardImage, Deck, User
from app.services import collector, job_queue, packs, progress, sources


def _jpeg(color=(40, 120, 60), size=(900, 700)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def _candidate(source_id, title, provider="commons", w=2000, h=1500, rank=0, cats=""):
    return {"provider": provider, "source_id": source_id, "page_url": f"https://example.org/{source_id}",
            "remote_url": f"https://example.org/{source_id}.jpg", "preview_url": None, "width": w, "height": h,
            "title": title, "author": "Jane Photographer", "license": "CC BY-SA 4.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "categories": cats,
            "description": "", "search_rank": rank}


@pytest.fixture
def fake_sources(monkeypatch):
    """Commons answers every query with a matching photo, a herbarium sheet and a map."""
    calls = {"download": 0, "fail_downloads": False, "unreachable": False}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def search(_client, query, limit=12):
        if calls["unreachable"]:
            raise sources.SourceError("Couldn't reach Wikimedia Commons (ConnectError).")
        slug = query.lower().replace(" ", "_")
        return [
            _candidate(f"File:{slug}_herbarium.jpg", f"{query} herbarium specimen", rank=0),
            _candidate(f"File:{slug}.jpg", query, rank=1),
            _candidate(f"File:{slug}_range_map.png", f"{query} range map", rank=2),
        ]

    monkeypatch.setattr(sources, "make_client", lambda: _Client())
    monkeypatch.setattr(sources, "commons_search", search)
    monkeypatch.setattr(sources, "commons_files", lambda _c, titles: [_candidate(t, t[5:] + " tree", rank=0) for t in titles])
    monkeypatch.setattr(sources, "wikipedia_lead_image", lambda _c, title: f"File:{title} lead.jpg")
    monkeypatch.setattr(sources, "wikipedia_summary", lambda _c, title: {
        "extract": f"{title} is a tree.", "url": f"https://en.wikipedia.org/wiki/{title}", "title": title})
    monkeypatch.setattr(sources, "inat_taxon_photos", lambda _c, name: [
        _candidate("123", f"{name}", provider="inaturalist", w=1024, h=768)])

    def download(_client, url, max_bytes=0):
        calls["download"] += 1
        if calls["fail_downloads"]:
            raise sources.SourceError("The picture couldn't be downloaded (404).")
        return _jpeg()

    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(collector, "PAUSE", 0)
    return calls


SMALL_PACK = {
    "slug": "test-trees", "title": "Test trees", "icon": "trees",
    "facets": [
        {"key": "overall", "label": "Tree", "queries": ["{search} tree"], "must": ["tree"], "inat": True},
        {"key": "bark", "label": "Bark", "queries": ["{search} bark"], "must": ["bark"]},
    ],
    "cards": [
        {"name": "White oak", "subtitle": "Quercus alba", "group": "Oaks", "wiki": "Quercus alba",
         "summary": "Rounded lobes.", "facts": [["Height", "60-100 ft"]], "cues": {"bark": "Pale plates"},
         "queries": {"bark": ["Quercus alba bark closeup"]}},
        {"name": "Sugar maple", "subtitle": "Acer saccharum", "wiki": "Acer saccharum", "summary": "Syrup."},
    ],
}


def _owner(make_user):
    client, user = make_user("owner")
    assert user["is_superuser"]
    return client


def _import(client, pack=SMALL_PACK):
    r = client.post("/api/v1/decks/import", json=pack)
    assert r.status_code == 200, r.text
    return r.json()["slug"]


# ------------------------------------------------------------------ packs

def test_shipped_trees_pack_is_valid_and_seeds():
    shipped = packs.shipped_packs()
    trees = next(p for p in shipped if p.slug == "midwest-trees")
    assert len(trees.cards) >= 30
    assert [f.key for f in trees.facets] == ["overall", "bark", "leaf", "fruit"]
    for card in trees.cards:
        assert card.subtitle and card.wiki and card.summary
        assert set(card.cues) == {"overall", "bark", "leaf", "fruit"}, card.name
    with SessionLocal() as db:
        packs.seed_shipped(db)
        packs.seed_shipped(db)  # idempotent
        deck = db.query(Deck).filter(Deck.slug == "midwest-trees").one()
        assert len(deck.cards) == len(trees.cards)
        assert db.query(Deck).count() == len(shipped)


def test_every_shipped_pack_has_unique_cards():
    for pack in packs.shipped_packs():
        slugs = [packs.slugify(c.name) for c in pack.cards]
        assert len(slugs) == len(set(slugs)), pack.slug


def test_facet_queries_use_card_queries_first():
    with SessionLocal() as db:
        deck = packs.apply_pack(db, packs.PackSpec.model_validate(SMALL_PACK))
        db.commit()
        oak = deck.cards[0]
        assert packs.facet_queries(deck, oak, deck.facets[1]) == ["Quercus alba bark closeup", "Quercus alba bark"]
        assert packs.facet_queries(deck, oak, deck.facets[0]) == ["Quercus alba tree"]


def test_reimport_keeps_cards_and_updates_text(make_user):
    client = _owner(make_user)
    _import(client)
    changed = {**SMALL_PACK, "cards": [{**SMALL_PACK["cards"][0], "summary": "New line."}, *SMALL_PACK["cards"][1:]]}
    _import(client, changed)
    deck = client.get("/api/v1/decks/test-trees").json()
    assert [c["summary"] for c in deck["cards"]] == ["New line.", "Syrup."]


def test_export_round_trips(make_user):
    client = _owner(make_user)
    _import(client)
    exported = client.get("/api/v1/decks/test-trees/export").json()
    assert exported["cards"][0]["queries"] == {"bark": ["Quercus alba bark closeup"]}
    assert packs.PackSpec.model_validate(exported).title == "Test trees"


def test_bad_pack_is_refused(make_user):
    client = _owner(make_user)
    r = client.post("/api/v1/decks/import", json={"title": "No cards", "facets": [{"key": "a", "label": "A"}], "cards": []})
    assert r.status_code == 400 and "isn't valid" in r.json()["detail"]


# ------------------------------------------------------------------ collecting

def test_collect_picks_the_matching_photo_and_downloads_it(make_user, fake_sources):
    client = _owner(make_user)
    _import(client)
    assert job_queue.drain() == 1
    deck = client.get("/api/v1/decks/test-trees").json()
    assert deck["collect"]["status"] == "done"
    oak = deck["cards"][0]
    assert oak["wiki_extract"] == "Quercus alba is a tree."
    # The article's lead picture wins the overall look; the herbarium sheet and the map never win.
    assert oak["images"]["overall"]["title"] == "Quercus alba lead.jpg tree"
    assert oak["images"]["bark"]["title"] == "Quercus alba bark closeup"
    assert oak["images"]["bark"]["license"] == "CC BY-SA 4.0" and oak["images"]["bark"]["author"]
    r = client.get(f"/api/v1/images/{oak['images']['bark']['id']}/file?size=thumb")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(r.content)) as thumb:
        assert max(thumb.size) <= 480
    assert deck["cover_image_id"] == oak["images"]["overall"]["id"]


def test_collect_again_keeps_pictures(make_user, fake_sources):
    client = _owner(make_user)
    _import(client)
    job_queue.drain()
    downloads = fake_sources["download"]
    client.post("/api/v1/decks/test-trees/collect", json={})
    job_queue.drain()
    assert fake_sources["download"] == downloads


def test_unreachable_sources_stop_with_a_clear_message(make_user, fake_sources):
    fake_sources["unreachable"] = True
    client = _owner(make_user)
    many = {**SMALL_PACK, "cards": [{"name": f"Tree {n}", "subtitle": f"Arbor {n}"} for n in range(5)]}
    _import(client, many)
    job_queue.drain()
    deck = client.get("/api/v1/decks/test-trees").json()
    assert deck["collect"]["status"] == "error"
    assert "commons.wikimedia.org" in deck["collect"]["message"]


def test_failed_downloads_fall_through_and_are_reported(make_user, fake_sources):
    fake_sources["fail_downloads"] = True
    client = _owner(make_user)
    _import(client)
    job_queue.drain()
    deck = client.get("/api/v1/decks/test-trees").json()
    assert deck["collect"]["status"] == "done"
    assert deck["cards"][0]["images"] == {}
    assert "could be downloaded" in deck["collect"]["message"]


def test_owner_can_choose_and_hide_pictures(make_user, fake_sources):
    client = _owner(make_user)
    _import(client)
    job_queue.drain()
    oak = client.get("/api/v1/decks/test-trees").json()["cards"][0]
    options = client.get(f"/api/v1/cards/{oak['id']}/images", params={"facet": "bark"}).json()
    assert options[0]["status"] == "chosen" and len(options) >= 3
    other = next(o for o in options if o["status"] == "candidate" and "map" not in o["title"])
    r = client.post(f"/api/v1/images/{other['id']}/choose")
    assert r.status_code == 200 and r.json()["picked_by_person"]
    oak = client.get("/api/v1/decks/test-trees").json()["cards"][0]
    assert oak["images"]["bark"]["id"] == other["id"]

    # A collection that looks again never replaces a person's pick.
    client.post("/api/v1/decks/test-trees/collect", json={"force": True})
    job_queue.drain()
    assert client.get("/api/v1/decks/test-trees").json()["cards"][0]["images"]["bark"]["id"] == other["id"]

    r = client.post(f"/api/v1/images/{other['id']}/hide")
    assert r.status_code == 200 and r.json()["replacement"]["id"] != other["id"]
    oak = client.get("/api/v1/decks/test-trees").json()["cards"][0]
    assert oak["images"]["bark"]["id"] == r.json()["replacement"]["id"]


def test_members_can_read_but_not_change_decks(make_user, fake_sources):
    owner = _owner(make_user)
    _import(owner)
    job_queue.drain()
    member, _ = make_user("someone")
    deck = member.get("/api/v1/decks/test-trees").json()
    image_id = deck["cards"][0]["images"]["bark"]["id"]
    assert member.get(f"/api/v1/images/{image_id}/file").status_code == 200
    assert member.post(f"/api/v1/images/{image_id}/hide").status_code == 403
    assert member.post("/api/v1/decks/test-trees/collect", json={}).status_code == 403
    assert member.post("/api/v1/decks/import", json=SMALL_PACK).status_code == 403
    assert member.delete("/api/v1/decks/test-trees").status_code == 403


def test_signed_out_people_see_nothing(anon_client):
    assert anon_client.get("/api/v1/decks").status_code == 401
    assert anon_client.get("/api/v1/images/1/file").status_code == 401


def test_delete_deck_removes_cards_and_files(make_user, fake_sources):
    from app.config import settings
    client = _owner(make_user)
    _import(client)
    job_queue.drain()
    assert (settings.images_dir / "test-trees").is_dir()
    assert client.delete("/api/v1/decks/test-trees").status_code == 200
    assert client.get("/api/v1/decks/test-trees").status_code == 404
    assert not (settings.images_dir / "test-trees").exists()
    with SessionLocal() as db:
        assert db.query(Card).count() == 0 and db.query(CardImage).count() == 0


# ------------------------------------------------------------------ scoring and parsing

def test_score_prefers_the_facet_and_avoids_sheets_and_maps():
    with SessionLocal() as db:
        deck = packs.apply_pack(db, packs.PackSpec.model_validate(SMALL_PACK))
        oak = deck.cards[0]
        bark = deck.facets[1]
        good = collector.score(_candidate("a", "Quercus alba bark in Ohio"), bark, oak)
        leaf = collector.score(_candidate("b", "Quercus alba leaves"), bark, oak)
        sheet = collector.score(_candidate("c", "Quercus alba bark herbarium sheet"), bark, oak)
        tiny = collector.score(_candidate("d", "Quercus alba bark", w=300, h=200), bark, oak)
        assert good > leaf > sheet
        assert good > tiny


@pytest.mark.parametrize("raw,expected", [
    ("CC BY-SA 4.0", "CC BY-SA 4.0"),
    ("CC BY 2.0", "CC BY 2.0"),
    ("CC BY-SA 3.0 de", "CC BY-SA 3.0"),
    ("CC0", "CC0"),
    ("Public domain", "Public domain"),
    ("CC BY-ND 4.0", None),
    ("GFDL", None),
    ("", None),
    ("CC BY-NC 4.0", "CC BY-NC 4.0"),
])
def test_normalize_license(raw, expected):
    assert sources.normalize_license(raw, "https://creativecommons.org/x") == expected


def test_noncommercial_can_be_turned_off(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ALLOW_NONCOMMERCIAL_IMAGES", False)
    assert sources.normalize_license("CC BY-NC-SA 4.0") is None
    assert sources.normalize_license("CC BY 4.0") == "CC BY 4.0"


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_commons_search_parses_and_filters_licences():
    def handler(request: httpx.Request):
        assert request.url.host == "commons.wikimedia.org"
        assert "filetype:bitmap" in request.url.params["gsrsearch"]
        meta = lambda lic, artist: {"LicenseShortName": {"value": lic}, "Artist": {"value": artist},  # noqa: E731
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                                    "Categories": {"value": "Quercus alba|Quality images"}}
        return httpx.Response(200, json={"query": {"pages": [
            {"title": "File:Oak bark.jpg", "index": 2, "imageinfo": [{
                "url": "https://upload.wikimedia.org/a/Oak_bark.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Oak_bark.jpg",
                "thumburl": "https://upload.wikimedia.org/thumb/a/Oak_bark.jpg/1600px-Oak_bark.jpg",
                "width": 3000, "height": 2000, "mime": "image/jpeg",
                "extmetadata": meta("CC BY-SA 4.0", '<a href="//commons.wikimedia.org/wiki/User:Ann">Ann &amp; Bo</a>')}]},
            {"title": "File:No derivs.jpg", "index": 1, "imageinfo": [{
                "url": "u", "thumburl": "t", "width": 3000, "height": 2000, "mime": "image/jpeg",
                "extmetadata": meta("CC BY-ND 4.0", "X")}]},
            {"title": "File:Drawing.svg", "index": 0, "imageinfo": [{
                "url": "u", "thumburl": "t", "width": 300, "height": 200, "mime": "image/svg+xml",
                "extmetadata": meta("CC0", "X")}]},
        ]}})

    with _mock_client(handler) as client:
        found = sources.commons_search(client, "Quercus alba bark")
    assert len(found) == 1
    c = found[0]
    assert c["author"] == "Ann & Bo" and c["license"] == "CC BY-SA 4.0"
    assert c["title"] == "Oak bark" and "quality images" in c["categories"]
    assert c["preview_url"].endswith("/400px-Oak_bark.jpg")


def test_inat_taxon_photos_parse():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/taxa":
            return httpx.Response(200, json={"results": [{"id": 9, "name": "Quercus alba"}]})
        assert request.url.path == "/v1/taxa/9"
        return httpx.Response(200, json={"results": [{"preferred_common_name": "White Oak", "taxon_photos": [
            {"photo": {"id": 1, "license_code": "cc-by-nc", "attribution": "(c) Jo Smith, some rights reserved (CC BY-NC)",
                       "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
                       "original_dimensions": {"width": 2048, "height": 1536}}},
            {"photo": {"id": 2, "license_code": None, "attribution": "(c) Al, all rights reserved",
                       "url": "https://static.inaturalist.org/photos/2/square.jpg"}},
        ]}]})

    with _mock_client(handler) as client:
        found = sources.inat_taxon_photos(client, "Quercus alba")
    assert len(found) == 1
    assert found[0]["author"] == "Jo Smith" and found[0]["license"] == "CC BY-NC 4.0"
    assert found[0]["remote_url"].endswith("/large.jpg")
    assert found[0]["page_url"] == "https://www.inaturalist.org/photos/1"


def test_unreachable_host_raises_source_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with _mock_client(handler) as client, pytest.raises(sources.SourceError, match="Couldn't reach"):
        sources.commons_search(client, "x")


# ------------------------------------------------------------------ progress

def test_progress_moves_through_boxes(make_user):
    client = _owner(make_user)
    _import(client)
    card_id = client.get("/api/v1/decks/test-trees").json()["cards"][0]["id"]
    r = client.post("/api/v1/progress", json={"card_id": card_id, "result": "knew"})
    assert r.json()["box"] == 1
    client.post("/api/v1/progress", json={"card_id": card_id, "result": "knew"})
    r = client.post("/api/v1/progress", json={"card_id": card_id, "result": "knew"})
    assert r.json()["box"] == 3
    deck = client.get("/api/v1/decks/test-trees").json()
    assert deck["progress"]["known"] == 1 and deck["progress"]["seen"] == 1
    r = client.post("/api/v1/progress", json={"card_id": card_id, "result": "again"})
    assert r.json()["box"] == 1

    # Progress is each person's own.
    other, _ = make_user("other")
    assert other.get("/api/v1/decks/test-trees").json()["progress"]["seen"] == 0


def test_quiz_order_puts_due_cards_first():
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)

    class C:
        def __init__(self, i):
            self.id = i

    class P:
        def __init__(self, due, seen=1):
            self.due_at, self.seen, self.box = due, seen, 1

    cards = [C(1), C(2), C(3), C(4)]
    rows = {1: P(now + timedelta(days=3)), 3: P(now - timedelta(hours=1)), 4: P(now - timedelta(days=2))}
    assert progress.quiz_order(cards, rows, 10, now=now) == [4, 3, 2, 1]
    assert progress.quiz_order(cards, rows, 2, now=now) == [4, 3]


def test_deck_of_the_day_rotates_through_decks_with_pictures(make_user, fake_sources):
    client = _owner(make_user)
    _import(client)
    _import(client, {**SMALL_PACK, "slug": "more-trees", "title": "More trees"})
    job_queue.drain()
    with SessionLocal() as db:
        packs.apply_pack(db, packs.PackSpec.model_validate({**SMALL_PACK, "slug": "empty", "title": "No pictures yet"}))
        db.commit()
        day = date(2026, 10, 24)
        picks = {progress.deck_of_the_day(db, day + timedelta(days=n)).slug for n in range(4)}
        assert picks == {"test-trees", "more-trees"}
        assert progress.deck_of_the_day(db, day).slug != progress.deck_of_the_day(db, day + timedelta(days=1)).slug
    today = client.get("/api/v1/today").json()
    assert today["deck"]["slug"] in ("test-trees", "more-trees")


# ------------------------------------------------------------------ drafting with Claude

def test_draft_needs_a_key(make_user):
    client = _owner(make_user)
    r = client.post("/api/v1/decks/draft", json={"topic": "Planets"})
    assert r.status_code == 400 and "Anthropic" in r.json()["detail"]


def test_draft_with_claude_returns_a_pack_to_review(make_user, monkeypatch):
    from app.services import llm

    class Block:
        type = "tool_use"
        input = {"title": "Planets", "facets": [{"key": "overall", "label": "Planet", "queries": ["{search} planet"]}],
                 "cards": [{"name": "Mars", "wiki": "Mars", "summary": "The red planet.", "cues": {"overall": "Rusty red"}}]}

    class Messages:
        def create(self, **kwargs):
            assert kwargs["tool_choice"]["name"] == "save_deck" and "Planets" in kwargs["messages"][0]["content"]
            return type("M", (), {"content": [Block()]})()

    monkeypatch.setattr(llm, "configured", lambda db: llm.LlmConfig("sk-test", "claude-test"))
    monkeypatch.setattr(llm, "make_client", lambda key: type("C", (), {"messages": Messages()})())
    client = _owner(make_user)
    r = client.post("/api/v1/decks/draft", json={"topic": "Planets", "count": 8})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["slug"] == "planets" and draft["cards"][0]["name"] == "Mars" and draft["_source"] == "ai"
    # Nothing is saved until it is imported.
    with SessionLocal() as db:
        assert db.query(Deck).filter(Deck.slug == "planets").first() is None
    _import(client, draft)
    with SessionLocal() as db:
        assert db.query(Deck).filter(Deck.slug == "planets").one().source == "ai"


def test_cli_collect(fake_sources, capsys):
    from app import cli
    assert cli.main(["collect", "nope"]) == 1
    assert "midwest-trees" in capsys.readouterr().out
    with SessionLocal() as db:
        packs.apply_pack(db, packs.PackSpec.model_validate(SMALL_PACK))
        db.commit()
    assert cli.main(["collect", "test-trees"]) == 0
    assert "done: 2 of 2 cards, 4 pictures." in capsys.readouterr().out
