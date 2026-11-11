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
