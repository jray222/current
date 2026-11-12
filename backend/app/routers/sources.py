import re
import time
import urllib.parse
from typing import Any, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.news import Category, Source, Article, CrawlRun, Vote
from app.routers._scoping import get_owned_or_404, ensure_category
from app.services import categories as category_service
from app.services import crawler as crawler_service

router = APIRouter(tags=["sources"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[-\s]+", "-", s)[:50] or "category"


class CategoryRead(BaseModel):
    id: int
    key: str
    label: str
    icon: str
    keywords: list[str]
    sort_order: int
    hidden: int
    unread_count: int = 0
    is_excluded: bool = False


class CategoryCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    key: Optional[str] = Field(None, max_length=50)
    icon: str = Field("newspaper", max_length=50)
    keywords: list[str] = Field(default_factory=list)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=50)
    keywords: Optional[list[str]] = None
    sort_order: Optional[int] = None
    hidden: Optional[int] = None


class SourceRead(BaseModel):
    id: int
    url: str
    name: str
    site_host: str
    favicon_url: Optional[str]
    fetch_mode: str
    feed_url: Optional[str]
    listing_url: Optional[str]
    link_pattern: Optional[str]
    link_selector: Optional[str]
    category_id: Optional[int]
    fetch_pages: int
    enabled: int
    crawl_status: str
    last_crawl_at: Optional[str]
    last_new_count: int
    last_error: Optional[str]
    fail_streak: int
    text_when: str
    text_method: str
    text_block_ads: int
    text_last_method: Optional[str]
    text_selector: Optional[str]
    article_count: int = 0


class SourceCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=1000)
    name: str = Field(..., min_length=1, max_length=200)
    favicon_url: Optional[str] = Field(None, max_length=1000)
    fetch_mode: Literal["rss", "html", "browser"] = "rss"
    feed_url: Optional[str] = Field(None, max_length=1000)
    listing_url: Optional[str] = Field(None, max_length=1000)
    link_pattern: Optional[str] = Field(None, max_length=500)
    link_selector: Optional[str] = Field(None, max_length=500)
    category_id: Optional[int] = None
    fetch_pages: int = 1
    enabled: int = 1
    text_when: Literal["open", "keep", "crawl"] = "open"
    text_method: Literal["auto", "http", "browser"] = "auto"
    text_block_ads: int = 1
    text_selector: Optional[str] = Field(None, max_length=500)


class SourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    favicon_url: Optional[str] = Field(None, max_length=1000)
    fetch_mode: Optional[Literal["rss", "html", "browser"]] = None
    feed_url: Optional[str] = Field(None, max_length=1000)
    listing_url: Optional[str] = Field(None, max_length=1000)
    link_pattern: Optional[str] = Field(None, max_length=500)
    link_selector: Optional[str] = Field(None, max_length=500)
    category_id: Optional[int] = None
    fetch_pages: Optional[int] = None
    enabled: Optional[int] = None
    text_when: Optional[Literal["open", "keep", "crawl"]] = None
    text_method: Optional[Literal["auto", "http", "browser"]] = None
    text_block_ads: Optional[int] = None
    text_selector: Optional[str] = Field(None, max_length=500)


class CrawlRunRead(BaseModel):
    id: int
    source_id: int
    trigger: str
    mode_used: Optional[str]
    status: str
    started_at: str
    finished_at: Optional[str]
    found: int
    new: int
    skipped_robots: int
    message: Optional[str]


class SourceProbePayload(BaseModel):
    url: str = Field(..., min_length=1, max_length=1000)


# --------------------------------------------------------------------------
# Category Endpoints
# --------------------------------------------------------------------------

@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category_service.seed_all(db, user.household_id)
    feed_prefs = user.feed_preferences or {}
    category_order = feed_prefs.get("category_order", [])
    excluded_set = set(feed_prefs.get("excluded_categories", []))

    categories = (
        db.query(Category)
        .filter(Category.household_id == user.household_id)
        .all()
    )

    if category_order:
        order_map = {k: i for i, k in enumerate(category_order)}
        categories.sort(key=lambda c: (order_map.get(c.key, 999), c.sort_order, c.id))
    else:
        categories.sort(key=lambda c: (c.sort_order, c.id))

    # Subquery: articles already triaged (keep or skip) by this user
    triaged_ids = (
        db.query(Vote.article_id)
        .filter(
            Vote.user_id == user.id,
            Vote.article_id.isnot(None),
            Vote.verdict.in_(["keep", "skip"]),
        )
        .scalar_subquery()
    )

    # Calculate unread counts per category for this user
    counts = dict(
        db.query(Article.category_id, func.count(Article.id))
        .filter(
            Article.household_id == user.household_id,
            ~Article.id.in_(triaged_ids),
        )
        .group_by(Article.category_id)
        .all()
    )

    results = []
    for c in categories:
        results.append(
            CategoryRead(
                id=c.id,
                key=c.key,
                label=c.label,
                icon=c.icon,
                keywords=c.keywords,
                sort_order=c.sort_order,
                hidden=c.hidden,
                unread_count=counts.get(c.id, 0),
                is_excluded=c.key in excluded_set,
            )
        )
    return results


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = _slugify(payload.key or payload.label)

    # Ensure key uniqueness within household
    existing = (
        db.query(Category)
        .filter(Category.household_id == user.household_id, Category.key == key)
        .first()
    )
    if existing:
        key = f"{key}-{int(time.time())}"[:50]

    cat = Category(
        household_id=user.household_id,
        key=key,
        label=payload.label.strip(),
        icon=payload.icon,
        sort_order=payload.sort_order,
        hidden=0,
    )
    cat.keywords = payload.keywords
    db.add(cat)
    db.commit()
    db.refresh(cat)

    return CategoryRead(
        id=cat.id,
        key=cat.key,
        label=cat.label,
        icon=cat.icon,
        keywords=cat.keywords,
        sort_order=cat.sort_order,
        hidden=cat.hidden,
        unread_count=0,
    )


@router.patch("/categories/{id}", response_model=CategoryRead)
def update_category(
    id: int,
    payload: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = get_owned_or_404(db, Category, id, user.household_id, "Category")

    if payload.label is not None:
        cat.label = payload.label.strip()
    if payload.icon is not None:
        cat.icon = payload.icon
    if payload.keywords is not None:
        cat.keywords = payload.keywords
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    if payload.hidden is not None:
        cat.hidden = payload.hidden

    db.commit()
    db.refresh(cat)

    return CategoryRead(
        id=cat.id,
        key=cat.key,
        label=cat.label,
        icon=cat.icon,
        keywords=cat.keywords,
        sort_order=cat.sort_order,
        hidden=cat.hidden,
        unread_count=0,
    )


@router.delete("/categories/{id}")
def delete_category(
    id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = get_owned_or_404(db, Category, id, user.household_id, "Category")
    if cat.key == "general":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The General category is protected and cannot be deleted.",
        )

    # Reassign any articles in this category to General
    general = category_service.get_general_category(db, user.household_id)
    db.query(Article).filter(
        Article.household_id == user.household_id,
        Article.category_id == cat.id,
    ).update({Article.category_id: general.id})

    # Clear category_id from any sources assigned to this category
    db.query(Source).filter(
        Source.household_id == user.household_id,
        Source.category_id == cat.id,
    ).update({Source.category_id: None})

    db.delete(cat)
    db.commit()
    return {"ok": True, "deleted": id, "reassigned_to": general.id}


# --------------------------------------------------------------------------
# Source Endpoints
# --------------------------------------------------------------------------

@router.get("/sources", response_model=list[SourceRead])
def list_sources(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sources = (
        db.query(Source)
        .filter(Source.household_id == user.household_id)
        .order_by(Source.name.asc())
        .all()
    )

    counts = dict(
        db.query(Article.source_id, func.count(Article.id))
        .filter(Article.household_id == user.household_id)
        .group_by(Article.source_id)
        .all()
    )

    results = []
    for s in sources:
        results.append(
            SourceRead(
                id=s.id,
                url=s.url,
                name=s.name,
                site_host=s.site_host,
                favicon_url=s.favicon_url,
                fetch_mode=s.fetch_mode,
                feed_url=s.feed_url,
                listing_url=s.listing_url,
                link_pattern=s.link_pattern,
                link_selector=s.link_selector,
                category_id=s.category_id,
                fetch_pages=s.fetch_pages,
                enabled=s.enabled,
                crawl_status=s.crawl_status,
                last_crawl_at=s.last_crawl_at.isoformat() if s.last_crawl_at else None,
                last_new_count=s.last_new_count,
                last_error=s.last_error,
                fail_streak=s.fail_streak,
                text_when=s.text_when,
                text_method=s.text_method,
                text_block_ads=s.text_block_ads,
                text_last_method=s.text_last_method,
                text_selector=s.text_selector,
                article_count=counts.get(s.id, 0),
            )
        )
    return results


@router.post("/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_category(db, payload.category_id, user.household_id)

    parsed = urllib.parse.urlparse(payload.url)
    site_host = parsed.netloc.lower()
    if not site_host:
        raise HTTPException(status_code=400, detail="Invalid source URL: missing host.")

    # Unique check on (household_id, site_host, feed_url, listing_url)
    existing = (
        db.query(Source)
        .filter(
            Source.household_id == user.household_id,
            Source.site_host == site_host,
            Source.feed_url == payload.feed_url,
            Source.listing_url == payload.listing_url,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A source with this host and feed/listing URL already exists in your household.",
        )

    src = Source(
        household_id=user.household_id,
        url=payload.url.strip(),
        name=payload.name.strip(),
        site_host=site_host,
        favicon_url=payload.favicon_url,
        fetch_mode=payload.fetch_mode,
        feed_url=payload.feed_url,
        listing_url=payload.listing_url,
        link_pattern=payload.link_pattern,
        link_selector=payload.link_selector,
        category_id=payload.category_id,
        fetch_pages=payload.fetch_pages,
        enabled=payload.enabled,
        crawl_status="idle",
        last_new_count=0,
        fail_streak=0,
        text_when=payload.text_when,
        text_method=payload.text_method,
        text_block_ads=payload.text_block_ads,
        text_selector=payload.text_selector,
        created_by=user.id,
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    return SourceRead(
        id=src.id,
        url=src.url,
        name=src.name,
        site_host=src.site_host,
        favicon_url=src.favicon_url,
        fetch_mode=src.fetch_mode,
        feed_url=src.feed_url,
        listing_url=src.listing_url,
        link_pattern=src.link_pattern,
        link_selector=src.link_selector,
        category_id=src.category_id,
        fetch_pages=src.fetch_pages,
        enabled=src.enabled,
        crawl_status=src.crawl_status,
        last_crawl_at=None,
        last_new_count=0,
        last_error=None,
        fail_streak=0,
        text_when=src.text_when,
        text_method=src.text_method,
        text_block_ads=src.text_block_ads,
        text_last_method=None,
        text_selector=src.text_selector,
        article_count=0,
    )


@router.patch("/sources/{id}", response_model=SourceRead)
def update_source(
    id: int,
    payload: SourceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    src = get_owned_or_404(db, Source, id, user.household_id, "Source")

    if payload.category_id is not None:
        ensure_category(db, payload.category_id, user.household_id)
        src.category_id = payload.category_id

    if payload.name is not None:
        src.name = payload.name.strip()
    if payload.favicon_url is not None:
        src.favicon_url = payload.favicon_url
    if payload.fetch_mode is not None:
        src.fetch_mode = payload.fetch_mode
    if payload.feed_url is not None:
        src.feed_url = payload.feed_url
    if payload.listing_url is not None:
        src.listing_url = payload.listing_url
    if payload.link_pattern is not None:
        src.link_pattern = payload.link_pattern
    if payload.link_selector is not None:
        src.link_selector = payload.link_selector
    if payload.fetch_pages is not None:
        src.fetch_pages = payload.fetch_pages
    if payload.enabled is not None:
        src.enabled = payload.enabled
    if payload.text_when is not None:
        src.text_when = payload.text_when
    if payload.text_method is not None:
        src.text_method = payload.text_method
    if payload.text_block_ads is not None:
        src.text_block_ads = payload.text_block_ads
    if payload.text_selector is not None:
        src.text_selector = payload.text_selector

    db.commit()
    db.refresh(src)

    count = (
        db.query(func.count(Article.id))
        .filter(Article.household_id == user.household_id, Article.source_id == src.id)
        .scalar()
        or 0
    )

    return SourceRead(
        id=src.id,
        url=src.url,
        name=src.name,
        site_host=src.site_host,
        favicon_url=src.favicon_url,
        fetch_mode=src.fetch_mode,
        feed_url=src.feed_url,
        listing_url=src.listing_url,
        link_pattern=src.link_pattern,
        link_selector=src.link_selector,
        category_id=src.category_id,
        fetch_pages=src.fetch_pages,
        enabled=src.enabled,
        crawl_status=src.crawl_status,
        last_crawl_at=src.last_crawl_at.isoformat() if src.last_crawl_at else None,
        last_new_count=src.last_new_count,
        last_error=src.last_error,
        fail_streak=src.fail_streak,
        text_when=src.text_when,
        text_method=src.text_method,
        text_block_ads=src.text_block_ads,
        text_last_method=src.text_last_method,
        text_selector=src.text_selector,
        article_count=count,
    )


@router.delete("/sources/{id}")
def delete_source(
    id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    src = get_owned_or_404(db, Source, id, user.household_id, "Source")
    db.delete(src)
    db.commit()
    return {"ok": True, "deleted": id}


@router.get("/sources/{id}/runs", response_model=list[CrawlRunRead])
def get_source_runs(
    id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    src = get_owned_or_404(db, Source, id, user.household_id, "Source")
    runs = (
        db.query(CrawlRun)
        .filter(CrawlRun.household_id == user.household_id, CrawlRun.source_id == src.id)
        .order_by(CrawlRun.id.desc())
        .limit(20)
        .all()
    )
    return [
        CrawlRunRead(
            id=r.id,
            source_id=r.source_id,
            trigger=r.trigger,
            mode_used=r.mode_used,
            status=r.status,
            started_at=r.started_at.isoformat(),
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
            found=r.found,
            new=r.new,
            skipped_robots=r.skipped_robots,
            message=r.message,
        )
        for r in runs
    ]


@router.post("/sources/probe")
def probe_source_url(
    payload: SourceProbePayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crawler_service.check_source(db, user.household_id, payload.url)


@router.post("/sources/{id}/crawl")
def trigger_source_crawl(
    id: int,
    force: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    src = get_owned_or_404(db, Source, id, user.household_id, "Source")
    crawler_service.enqueue_source_crawl(src.id, trigger="manual")
    return {"ok": True, "source_id": src.id, "status": "queued"}


@router.post("/crawl")
def trigger_household_crawl(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = crawler_service.crawl_household(user.household_id, trigger="manual")
    return {"ok": True, "queued_count": count}
