"""Safely downloads, resizes, and stores article thumbnails with directory traversal protection.
"""
import hashlib
import io
import os
from pathlib import Path
from typing import Optional
from PIL import Image

from app.config import settings
from app.database import SessionLocal
from app.models.news import Article
from app.services.safe_fetch import safe_fetch
from app.services import job_queue


def get_image_absolute_path(rel_path: str) -> Optional[Path]:
    """Resolves a relative image path, ensuring it stays strictly within the images directory."""
    if not rel_path or ".." in rel_path:
        return None
    base = settings.images_dir.resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)):
        return None
    return target


def process_and_save_image(image_bytes: bytes, household_id: int) -> Optional[str]:
    """Validates image bytes, resizes to max 720px, converts to JPEG, and stores on disk."""
    if not image_bytes:
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
    except Exception:
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Handle RGBA/transparency
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Proportionally downscale if larger than 720px
            max_size = 720
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=85, optimize=True)
            jpeg_bytes = out_buf.getvalue()
    except Exception:
        return None

    file_hash = hashlib.sha256(jpeg_bytes).hexdigest()[:20]
    rel_path = f"{household_id}/{file_hash}.jpg"

    dest_dir = settings.images_dir / str(household_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{file_hash}.jpg"

    with open(dest_file, "wb") as f:
        f.write(jpeg_bytes)

    return rel_path


def download_and_store_thumb(household_id: int, remote_url: str) -> Optional[str]:
    """Safely downloads a remote image and processes it into a thumbnail."""
    if not remote_url:
        return None
    try:
        res = safe_fetch(
            remote_url,
            max_bytes=10 * 1024 * 1024,
            timeout=10.0,
            check_robots=False,
        )
        if res.status_code != 200:
            return None
        return process_and_save_image(res.content, household_id)
    except Exception:
        return None


def delete_image(rel_path: str) -> None:
    """Removes a stored thumbnail from disk."""
    abs_path = get_image_absolute_path(rel_path)
    if abs_path and abs_path.is_file():
        try:
            abs_path.unlink()
        except OSError:
            pass


def _download_article_image_job(article_id: int) -> None:
    """Background worker job to fetch and store thumbnail for an article."""
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if not article or not article.image_remote_url or article.thumb_path:
            return

        thumb = download_and_store_thumb(article.household_id, article.image_remote_url)
        if thumb:
            article.thumb_path = thumb
            db.commit()


job_queue.register("download_article_image", _download_article_image_job)
