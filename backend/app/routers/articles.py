"""Article endpoints: metadata, reader views, and on-demand full-text extraction.
"""
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.news import Article, Source, Vote
from app.routers._scoping import get_owned_or_404
from app.services import job_queue
from app.services.job_queue import Priority
from app.services.fulltext import fetch_article_text

router = APIRouter(tags=["articles"])


class OpenByUrlRequest(BaseModel):
    url: str
    title: Optional[str] = None
    summary: Optional[str] = None
    image_remote_url: Optional[str] = None
    source_id: Optional[int] = None
    category_id: Optional[int] = None


class OpenByUrlResponse(BaseModel):
    id: int
    title: str


class ArticleRead(BaseModel):
    id: int
    household_id: int
    source_id: int
    category_id: Optional[int]
    url: str
    canonical_url: Optional[str]
    story_id: str
    title: str
    summary: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    discovered_at: str
    image_remote_url: Optional[str]
    thumb_path: Optional[str]
    lang: str
    text_status: str
    text_method: Optional[str]
    text_pages: int
    word_count: int
    text_blocks: Optional[list[dict[str, Any]]]
    source_name: Optional[str]
    source_host: Optional[str]
    source_favicon: Optional[str]
    user_vote: Optional[str] = None


def _to_article_read(article: Article, user_id: int, db: Session) -> ArticleRead:
    source = db.get(Source, article.source_id) if article.source_id else None
    vote = (
        db.query(Vote.verdict)
        .filter(Vote.user_id == user_id, Vote.article_id == article.id)
        .first()
    )
    user_vote = vote[0] if vote else None

    return ArticleRead(
        id=article.id,
        household_id=article.household_id,
        source_id=article.source_id,
        category_id=article.category_id,
        url=article.url,
        canonical_url=article.canonical_url,
        story_id=article.story_id,
        title=article.title,
        summary=article.summary,
        author=article.author,
        published_at=article.published_at.isoformat() if article.published_at else None,
        discovered_at=article.discovered_at.isoformat() if article.discovered_at else "",
        image_remote_url=article.image_remote_url,
        thumb_path=article.thumb_path,
        lang=article.lang,
        text_status=article.text_status,
        text_method=article.text_method,
        text_pages=article.text_pages,
        word_count=article.word_count,
        text_blocks=article.text_blocks,
        source_name=source.name if source else None,
        source_host=source.site_host if source else None,
        source_favicon=source.favicon_url if source else None,
        user_vote=user_vote,
    )


@router.get("/articles/{id}", response_model=ArticleRead)
def get_article(
    id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = get_owned_or_404(db, Article, id, user.household_id, "Article")
    return _to_article_read(article, user.id, db)


@router.post("/articles/{id}/fetch-text", response_model=ArticleRead)
def request_article_text(
    id: int,
    force: bool = False,
    sync: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = get_owned_or_404(db, Article, id, user.household_id, "Article")

    if sync or job_queue._is_manual():
        fetch_article_text(article.id, force=force)
        db.refresh(article)
    else:
        article.text_status = "queued"
        db.commit()
        job_queue.enqueue(
            "fulltext",
            article.id,
            priority=Priority.HIGH,
            dedupe_key=f"text-{article.id}",
        )
        db.refresh(article)

    return _to_article_read(article, user.id, db)


@router.post("/articles/open-by-url", response_model=OpenByUrlResponse)
def open_by_url(
    payload: OpenByUrlRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves an existing article by URL or dynamically ingests it on-demand for reader viewing."""
    from datetime import datetime, timezone
    import urllib.parse
    import logging
    from app.services.dedupe import canonical_url, find_or_create_story_id, url_hash
    from app.services.categories import get_general_category, keyword_categorize
    from app.models.news import Category

    logger = logging.getLogger("current.articles")
    c_url = canonical_url(payload.url)
    h_id = user.household_id

    # 1. Check if article already exists for this household
    existing = (
        db.query(Article)
        .filter(Article.household_id == h_id, Article.canonical_url == c_url)
        .first()
    )
    if existing:
        return OpenByUrlResponse(id=existing.id, title=existing.title)

    # 2. Determine source_id if not supplied
    source_id = payload.source_id
    if not source_id:
        parsed = urllib.parse.urlparse(payload.url)
        host = parsed.netloc.lower().removeprefix("www.")
        matching_source = (
            db.query(Source)
            .filter(
                Source.household_id == h_id,
                (Source.site_host == host) | (Source.site_host == parsed.netloc.lower())
            )
            .first()
        )
        if matching_source:
            source_id = matching_source.id
        else:
            source_name = host.capitalize() if host else "Web Article"
            src = Source(
                household_id=h_id,
                url=f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else payload.url,
                name=source_name,
                site_host=host or "unknown",
                fetch_mode="browser",
                enabled=1,
            )
            db.add(src)
            db.flush()
            source_id = src.id

    # 3. Auto-assign category if not provided
    category_id = payload.category_id
    if not category_id:
        categories = db.query(Category).filter(Category.household_id == h_id).all()
        general_cat = get_general_category(db, h_id)
        category_id = keyword_categorize(payload.title or "", payload.summary or "", [], categories, general_cat.id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    story_id = find_or_create_story_id(db, h_id, payload.title or payload.url, reference_time=now)
    u_hash = url_hash(payload.url)

    new_article = Article(
        household_id=h_id,
        source_id=source_id,
        category_id=category_id,
        url=payload.url,
        canonical_url=c_url,
        url_hash=u_hash,
        story_id=story_id,
        title=payload.title or "Untitled Story",
        summary=payload.summary,
        image_remote_url=payload.image_remote_url,
        discovered_at=now,
        text_status="none",
    )
    db.add(new_article)
    db.commit()
    db.refresh(new_article)

    # 4. Trigger fulltext extraction immediately
    try:
        fetch_article_text(new_article.id)
        db.refresh(new_article)
    except Exception as e:
        logger.warning(f"Could not extract text immediately for {new_article.id}: {e}")

    return OpenByUrlResponse(id=new_article.id, title=new_article.title)

