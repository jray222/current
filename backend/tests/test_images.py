import io
from PIL import Image
from app.database import SessionLocal
from app.models.news import Article, Source
from app.services import images
from app.services.images import (
    _download_article_image_job,
    process_and_save_image,
    get_image_absolute_path,
    delete_image,
)


def _generate_test_image_bytes(width=800, height=600, color="blue", format="PNG"):
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_process_and_save_image_resizes():
    raw_bytes = _generate_test_image_bytes(width=1200, height=800)
    rel_path = process_and_save_image(raw_bytes, household_id=99)
    assert rel_path is not None
    assert rel_path.startswith("99/")
    assert rel_path.endswith(".jpg")

    abs_path = get_image_absolute_path(rel_path)
    assert abs_path is not None
    assert abs_path.is_file()

    # Verify resized dimensions
    with Image.open(abs_path) as saved_img:
        assert saved_img.format == "JPEG"
        assert saved_img.width <= 720
        assert saved_img.height <= 720

    # Cleanup
    delete_image(rel_path)
    assert not abs_path.is_file()


def test_directory_traversal_protection():
    # Attempt directory traversal
    traversal_path = "../../../etc/passwd"
    resolved = get_image_absolute_path(traversal_path)
    assert resolved is None

    null_path = get_image_absolute_path("")
    assert null_path is None


def test_cross_household_thumbnail_reuse_isolated(make_user, monkeypatch):
    _, user_a = make_user("img_a", "Household Img A")
    _, user_b = make_user("img_b", "Household Img B")

    raw_bytes = _generate_test_image_bytes(width=400, height=300)
    download_calls = 0

    def mock_download(household_id, remote_url):
        nonlocal download_calls
        download_calls += 1
        return process_and_save_image(raw_bytes, household_id)

    monkeypatch.setattr(images, "download_and_store_thumb", mock_download)

    with SessionLocal() as db:
        src_a = Source(
            household_id=user_a["household_id"],
            url="https://img.example.com",
            name="Img A",
            site_host="img.example.com",
        )
        src_b = Source(
            household_id=user_b["household_id"],
            url="https://img.example.com",
            name="Img B",
            site_host="img.example.com",
        )
        db.add_all([src_a, src_b])
        db.flush()

        art_a = Article(
            household_id=user_a["household_id"],
            source_id=src_a.id,
            url="https://img.example.com/1",
            canonical_url="https://img.example.com/1",
            url_hash="img-h-1",
            story_id="img-s-1",
            title="Pic Story",
            image_remote_url="https://img.example.com/photo.jpg",
        )
        art_b = Article(
            household_id=user_b["household_id"],
            source_id=src_b.id,
            url="https://img.example.com/1",
            canonical_url="https://img.example.com/1",
            url_hash="img-h-1",
            story_id="img-s-2",
            title="Pic Story",
            image_remote_url="https://img.example.com/photo.jpg",
        )
        db.add_all([art_a, art_b])
        db.commit()
        art_a_id, art_b_id = art_a.id, art_b.id

    _download_article_image_job(art_a_id)
    assert download_calls == 1

    _download_article_image_job(art_b_id)
    assert download_calls == 1

    with SessionLocal() as db:
        a = db.get(Article, art_a_id)
        b = db.get(Article, art_b_id)
        assert a.thumb_path.startswith(f"{user_a['household_id']}/")
        assert b.thumb_path.startswith(f"{user_b['household_id']}/")
        assert a.thumb_path != b.thumb_path
        path_a = get_image_absolute_path(a.thumb_path)
        path_b = get_image_absolute_path(b.thumb_path)
        assert path_a.is_file() and path_b.is_file()

        # Deleting Household A's thumbnail leaves Household B's intact
        delete_image(a.thumb_path)
        assert not path_a.is_file()
        assert path_b.is_file()
