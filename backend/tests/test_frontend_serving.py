"""
After an update, a browser holding the old index.html asks for asset files
that no longer exist and pages go blank. index.html
must always be re-checked with the server; hashed assets may be kept forever.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import FOREVER, REVALIDATE, serve_frontend


def _client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<script src="/assets/index-abc123.js"></script>')
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    app = FastAPI()
    serve_frontend(app, tmp_path)
    return TestClient(app)


def test_index_html_is_always_rechecked(tmp_path):
    client = _client(tmp_path)
    for path in ("/", "/decks", "/decks/midwest-trees"):
        r = client.get(path)
        assert r.status_code == 200
        assert "index-abc123.js" in r.text
        assert r.headers["cache-control"] == REVALIDATE


def test_hashed_assets_are_cached_for_good(tmp_path):
    r = _client(tmp_path).get("/assets/index-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == FOREVER


def test_missing_asset_is_a_404_not_cached(tmp_path):
    # An old page asking for a file from before the update gets a clean 404
    # (which the app answers by reloading), never index.html and never cached.
    r = _client(tmp_path).get("/assets/DeckView-old999.js")
    assert r.status_code == 404
    assert "cache-control" not in r.headers


def test_other_root_files_and_api_paths(tmp_path):
    client = _client(tmp_path)
    r = client.get("/favicon.svg")
    assert r.status_code == 200 and r.headers["cache-control"] == REVALIDATE
    assert client.get("/api/v1/nope").status_code == 404
