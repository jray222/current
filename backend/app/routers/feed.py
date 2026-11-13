"""Feed and voting endpoints: editorial frontpage, category streams, swipe voting, undo, and kept reading list.
"""
from typing import Optional, Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.news import Article, Category, Source, Vote
from app.routers._scoping import get_owned_or_404
from app.routers.sources import CategoryRead
from app.services import categories as category_service
from app.services import interest
from app.services import job_queue
from app.services.job_queue import Priority

router = APIRouter(tags=["feed"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class AlsoInSource(BaseModel):
    article_id: int
    source_id: int
    source_name: str
    site_host: str
    favicon_url: Optional[str] = None


class FeedArticleItem(BaseModel):
    id: int
    title: str
    summary: Optional[str]
    url: str
    author: Optional[str]
    published_at: Optional[str]
    discovered_at: str
    thumb_path: Optional[str]
    image_remote_url: Optional[str]
    source_id: int
    source_name: str
    source_host: str
    source_favicon: Optional[str]
    category_id: Optional[int]
    category_key: Optional[str]
    category_label: Optional[str]
    story_id: str
    also_in: list[AlsoInSource] = Field(default_factory=list)
    predicted_score: float = 0.5
    text_status: str
    word_count: int
    is_opened: bool = False


class FrontPageSection(BaseModel):
    category: CategoryRead
    articles: list[FeedArticleItem]


class FrontPageResponse(BaseModel):
    lead_story: Optional[FeedArticleItem]
    sections: list[FrontPageSection]


class VotePayload(BaseModel):
    article_id: int
    verdict: Literal["keep", "skip", "open", "dislike"]


class KeptStatePayload(BaseModel):
    kept_state: Literal["unread", "read", "removed"]


class KeptArticleItem(BaseModel):
    article: FeedArticleItem
    kept_state: str
    saved_at: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _group_stories_and_build_items(
    ranked_articles: list[tuple[Article, float]],
    sources_by_id: dict[int, Source],
    categories_by_id: dict[int, Category],
    opened_ids: Optional[set[int]] = None,
) -> list[FeedArticleItem]:
    """Groups multiple articles on the same story, keeping the highest-ranked article
    as primary and listing others in `also_in`.
    """
    story_map: dict[str, FeedArticleItem] = {}
    items: list[FeedArticleItem] = []
    opened_set = opened_ids or set()

    for art, score in ranked_articles:
        src = sources_by_id.get(art.source_id)
        cat = categories_by_id.get(art.category_id)
        src_name = src.name if src else "Unknown"
        src_host = src.site_host if src else ""
        src_fav = src.favicon_url if src else None

        if art.story_id in story_map:
            # Sibling article on the same story
            primary = story_map[art.story_id]
            primary.also_in.append(
                AlsoInSource(
                    article_id=art.id,
                    source_id=art.source_id,
                    source_name=src_name,
                    site_host=src_host,
                    favicon_url=src_fav,
                )
            )
        else:
            item = FeedArticleItem(
                id=art.id,
                title=art.title,
                summary=art.summary,
                url=art.url,
                author=art.author,
                published_at=art.published_at.isoformat() if art.published_at else None,
                discovered_at=art.discovered_at.isoformat() if art.discovered_at else "",
                thumb_path=art.thumb_path,
                image_remote_url=art.image_remote_url,
                source_id=art.source_id,
                source_name=src_name,
                source_host=src_host,
                source_favicon=src_fav,
                category_id=art.category_id,
                category_key=cat.key if cat else "general",
                category_label=cat.label if cat else "General",
                story_id=art.story_id,
                also_in=[],
                predicted_score=round(score, 4),
                text_status=art.text_status,
                word_count=art.word_count,
                is_opened=bool(art.id in opened_set),
            )
            story_map[art.story_id] = item
            items.append(item)

    return items


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.get("/frontpage", response_model=FrontPageResponse)
def get_frontpage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category_service.seed_all(db, user.household_id)

    feed_prefs = user.feed_preferences or {}
    category_order = feed_prefs.get("category_order", [])
    excluded_set = set(feed_prefs.get("excluded_categories", []))

    # 1. Fetch categories for user
    categories = (
        db.query(Category)
        .filter(Category.household_id == user.household_id, Category.hidden == 0)
        .all()
    )

    # Filter out categories excluded by user
    if excluded_set:
        categories = [c for c in categories if c.key not in excluded_set]

    # Sort categories according to user custom order if set, else Category.sort_order
    if category_order:
        order_map = {k: i for i, k in enumerate(category_order)}
        categories.sort(key=lambda c: (order_map.get(c.key, 999), c.sort_order, c.id))
    else:
        categories.sort(key=lambda c: (c.sort_order, c.id))

    categories_by_id = {c.id: c for c in categories}

    # 2. Subquery: articles already triaged (keep, skip, or dislike) by this user
    triaged_ids = (
        db.query(Vote.article_id)
        .filter(
            Vote.user_id == user.id,
            Vote.article_id.isnot(None),
            Vote.verdict.in_(interest.TRIAGED_VERDICTS),
        )
        .scalar_subquery()
    )

    # Opened article IDs for visual read state
    opened_rows = (
        db.query(Vote.article_id)
        .filter(
            Vote.user_id == user.id,
            Vote.article_id.isnot(None),
            Vote.verdict == "open",
        )
        .all()
    )
    opened_ids = {row[0] for row in opened_rows}

    # 3. Candidate unvoted articles for this household
    articles = (
        db.query(Article)
        .filter(
            Article.household_id == user.household_id,
            ~Article.id.in_(triaged_ids),
        )
        .order_by(Article.discovered_at.desc())
        .limit(300)
        .all()
    )

    if not articles:
        return FrontPageResponse(lead_story=None, sections=[])

    # 4. Fetch sources
    source_ids = {a.source_id for a in articles}
    sources = db.query(Source).filter(Source.id.in_(source_ids)).all()
    sources_by_id = {s.id: s for s in sources}

    # 5. Rank all candidate articles
    ranked = interest.rank_articles_for_user(
        db, user.id, user.household_id, articles, sources_by_id, categories_by_id
    )
    all_story_items = _group_stories_and_build_items(ranked, sources_by_id, categories_by_id, opened_ids=opened_ids)

    if not all_story_items:
        return FrontPageResponse(lead_story=None, sections=[])

    # 6. Lead story: highest ranked article overall
    lead_story = all_story_items[0]
    lead_story_id = lead_story.story_id

    # 7. Group into sections by category
    sections: list[FrontPageSection] = []

    # Lead / Top Stories section
    top_cat = next((c for c in categories if c.key == "top-stories"), None)
    if top_cat:
        top_articles = [item for item in all_story_items if item.story_id != lead_story_id][:6]
        if top_articles:
            sections.append(
                FrontPageSection(
                    category=CategoryRead(
                        id=top_cat.id,
                        key=top_cat.key,
                        label=top_cat.label,
                        icon=top_cat.icon,
                        keywords=top_cat.keywords,
                        sort_order=top_cat.sort_order,
                        hidden=top_cat.hidden,
                        unread_count=len(top_articles),
                    ),
                    articles=top_articles,
                )
            )

    # Specific category sections
    used_story_ids = {lead_story_id} | {a.story_id for s in sections for a in s.articles}

    for cat in categories:
        if cat.key == "top-stories":
            continue
        cat_items = [
            item for item in all_story_items
            if item.category_id == cat.id and item.story_id not in used_story_ids
        ][:6]

        if cat_items:
            for it in cat_items:
                used_story_ids.add(it.story_id)
            sections.append(
                FrontPageSection(
                    category=CategoryRead(
                        id=cat.id,
                        key=cat.key,
                        label=cat.label,
                        icon=cat.icon,
                        keywords=cat.keywords,
                        sort_order=cat.sort_order,
                        hidden=cat.hidden,
                        unread_count=len(cat_items),
                    ),
                    articles=cat_items,
                )
            )

    return FrontPageResponse(lead_story=lead_story, sections=sections)


@router.get("/feed", response_model=list[FeedArticleItem])
def get_category_feed(
    category: Optional[str] = Query(None, description="Category key"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    triaged_ids = (
        db.query(Vote.article_id)
        .filter(
            Vote.user_id == user.id,
            Vote.article_id.isnot(None),
            Vote.verdict.in_(interest.TRIAGED_VERDICTS),
        )
        .scalar_subquery()
    )

    query = db.query(Article).filter(
        Article.household_id == user.household_id,
        ~Article.id.in_(triaged_ids),
    )

    target_cat_id = None
    if category and category != "top-stories":
        cat = (
            db.query(Category)
            .filter(Category.household_id == user.household_id, Category.key == category)
            .first()
        )
        if cat:
            target_cat_id = cat.id
            query = query.filter(Article.category_id == cat.id)

    articles = query.order_by(Article.discovered_at.desc()).limit(150).all()
    if not articles:
        return []

    source_ids = {a.source_id for a in articles}
    sources = db.query(Source).filter(Source.id.in_(source_ids)).all()
    sources_by_id = {s.id: s for s in sources}

    categories = db.query(Category).filter(Category.household_id == user.household_id).all()
    categories_by_id = {c.id: c for c in categories}

    opened_rows = (
        db.query(Vote.article_id)
        .filter(
            Vote.user_id == user.id,
            Vote.article_id.isnot(None),
            Vote.verdict == "open",
        )
        .all()
    )
    opened_ids = {row[0] for row in opened_rows}

    ranked = interest.rank_articles_for_user(
        db, user.id, user.household_id, articles, sources_by_id, categories_by_id
    )
    items = _group_stories_and_build_items(ranked, sources_by_id, categories_by_id, opened_ids=opened_ids)
    return items[offset : offset + limit]


@router.post("/votes")
def cast_vote(
    payload: VotePayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = get_owned_or_404(db, Article, payload.article_id, user.household_id, "Article")
    source = db.get(Source, article.source_id) if article.source_id else None
    cat = db.get(Category, article.category_id) if article.category_id else None

    # Snapshot features
    features = interest.extract_features(
        article,
        source_host=source.site_host if source else None,
        category_key=cat.key if cat else None,
    )

    # Check existing vote
    vote = (
        db.query(Vote)
        .filter(Vote.user_id == user.id, Vote.article_id == article.id)
        .first()
    )
    if vote is not None:
        # Opening an already-kept or already-opened article should not erase keep status or double-train
        if payload.verdict == "open" and vote.verdict in ("keep", "open"):
            return {
                "ok": True,
                "verdict": vote.verdict,
                "article_id": article.id,
                "story_id": article.story_id,
            }
        if vote.verdict == payload.verdict:
            return {
                "ok": True,
                "verdict": vote.verdict,
                "article_id": article.id,
                "story_id": article.story_id,
            }

        prev_verdict = vote.verdict
        vote.verdict = payload.verdict
        vote.kept_state = "unread" if payload.verdict == "keep" else "removed"
        vote.features = features
        vote.feature_version = interest.FEATURE_VERSION
        db.commit()

        if prev_verdict in ("keep", "open", "dislike"):
            interest.retrain_user_model(db, user.id)
        else:
            interest.update_model_online(
                db,
                user_id=user.id,
                household_id=user.household_id,
                features=features,
                verdict=payload.verdict,
            )
    else:
        vote = Vote(
            user_id=user.id,
            household_id=user.household_id,
            article_id=article.id,
            story_id=article.story_id,
            verdict=payload.verdict,
            weight=1.0,
            features_raw="{}",
            feature_version=interest.FEATURE_VERSION,
            kept_state="unread" if payload.verdict == "keep" else "removed",
        )
        vote.features = features
        db.add(vote)
        db.commit()

        # Online model learning step
        interest.update_model_online(
            db,
            user_id=user.id,
            household_id=user.household_id,
            features=features,
            verdict=payload.verdict,
        )

    # If keep and source has text_when == "keep": fetch full text
    if payload.verdict == "keep" and source and source.text_when == "keep":
        if article.text_status == "none":
            job_queue.enqueue(
                "fulltext",
                article.id,
                priority=Priority.HIGH,
                dedupe_key=f"text-{article.id}",
            )

    return {
        "ok": True,
        "verdict": payload.verdict,
        "article_id": article.id,
        "story_id": article.story_id,
    }


@router.delete("/votes/{article_id}")
def undo_vote(
    article_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vote = (
        db.query(Vote)
        .filter(Vote.user_id == user.id, Vote.article_id == article_id)
        .first()
    )
    if not vote:
        raise HTTPException(status_code=404, detail="Vote not found.")

    db.delete(vote)
    db.commit()

    # Retrain model without this vote
    interest.retrain_user_model(db, user.id)
    return {"ok": True, "undone_article_id": article_id}


@router.get("/kept", response_model=list[KeptArticleItem])
def get_kept_articles(
    status_filter: Literal["all", "unread", "read"] = Query("all", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Vote, Article)
        .join(Article, Vote.article_id == Article.id)
        .filter(
            Vote.user_id == user.id,
            Vote.verdict == "keep",
            Vote.kept_state != "removed",
        )
    )

    if status_filter != "all":
        query = query.filter(Vote.kept_state == status_filter)

    results = query.order_by(Vote.updated_at.desc()).offset(offset).limit(limit).all()
    if not results:
        return []

    source_ids = {art.source_id for _v, art in results}
    sources = db.query(Source).filter(Source.id.in_(source_ids)).all()
    sources_by_id = {s.id: s for s in sources}

    categories = db.query(Category).filter(Category.household_id == user.household_id).all()
    categories_by_id = {c.id: c for c in categories}

    items = []
    for vote, art in results:
        src = sources_by_id.get(art.source_id)
        cat = categories_by_id.get(art.category_id)
        feed_item = FeedArticleItem(
            id=art.id,
            title=art.title,
            summary=art.summary,
            url=art.url,
            author=art.author,
            published_at=art.published_at.isoformat() if art.published_at else None,
            discovered_at=art.discovered_at.isoformat() if art.discovered_at else "",
            thumb_path=art.thumb_path,
            image_remote_url=art.image_remote_url,
            source_id=art.source_id,
            source_name=src.name if src else "Unknown",
            source_host=src.site_host if src else "",
            source_favicon=src.favicon_url if src else None,
            category_id=art.category_id,
            category_key=cat.key if cat else "general",
            category_label=cat.label if cat else "General",
            story_id=art.story_id,
            also_in=[],
            predicted_score=1.0,
            text_status=art.text_status,
            word_count=art.word_count,
        )
        items.append(
            KeptArticleItem(
                article=feed_item,
                kept_state=vote.kept_state,
                saved_at=vote.updated_at.isoformat(),
            )
        )

    return items


@router.patch("/kept/{article_id}")
def update_kept_state(
    article_id: int,
    payload: KeptStatePayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vote = (
        db.query(Vote)
        .filter(Vote.user_id == user.id, Vote.article_id == article_id, Vote.verdict == "keep")
        .first()
    )
    if not vote:
        raise HTTPException(status_code=404, detail="Kept article not found.")

    vote.kept_state = payload.kept_state
    db.commit()
    return {"ok": True, "article_id": article_id, "kept_state": payload.kept_state}
