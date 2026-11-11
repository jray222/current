import re
from typing import Optional
from sqlalchemy.orm import Session
from app.models.news import Category, Article
from app.models.household import Household

DEFAULT_CATEGORIES: list[dict] = [
    {
        "key": "top-stories",
        "label": "Top stories",
        "icon": "flame",
        "keywords": ["breaking", "top", "headline", "lead"],
        "sort_order": 10,
    },
    {
        "key": "world",
        "label": "World",
        "icon": "globe",
        "keywords": ["world", "international", "global", "europe", "asia", "africa", "americas", "middle east", "ukraine", "un", "nato"],
        "sort_order": 20,
    },
    {
        "key": "us",
        "label": "U.S.",
        "icon": "flag",
        "keywords": ["u.s.", "us", "united states", "america", "federal", "national", "state"],
        "sort_order": 30,
    },
    {
        "key": "politics",
        "label": "Politics",
        "icon": "landmark",
        "keywords": ["politics", "election", "congress", "senate", "white house", "president", "biden", "trump", "campaign", "governor", "democrat", "republican"],
        "sort_order": 40,
    },
    {
        "key": "business",
        "label": "Business",
        "icon": "briefcase",
        "keywords": ["business", "economy", "market", "stock", "finance", "trade", "inflation", "fed", "bank", "earnings", "ceo", "revenue"],
        "sort_order": 50,
    },
    {
        "key": "tech",
        "label": "Tech",
        "icon": "cpu",
        "keywords": ["tech", "technology", "ai", "artificial intelligence", "software", "apple", "google", "microsoft", "meta", "nvidia", "cybersecurity", "startup"],
        "sort_order": 60,
    },
    {
        "key": "science",
        "label": "Science",
        "icon": "flask-conical",
        "keywords": ["science", "space", "nasa", "physics", "biology", "climate", "environment", "earth", "research", "astronomy"],
        "sort_order": 70,
    },
    {
        "key": "health",
        "label": "Health",
        "icon": "heart-pulse",
        "keywords": ["health", "medicine", "medical", "doctor", "hospital", "fda", "cdc", "virus", "wellness", "diet", "mental health"],
        "sort_order": 80,
    },
    {
        "key": "sports",
        "label": "Sports",
        "icon": "trophy",
        "keywords": ["sports", "nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball", "baseball", "olympics", "championship"],
        "sort_order": 90,
    },
    {
        "key": "local",
        "label": "Local",
        "icon": "map-pin",
        "keywords": ["local", "city", "county", "community", "transit", "neighborhood", "municipal"],
        "sort_order": 100,
    },
    {
        "key": "culture",
        "label": "Culture",
        "icon": "palette",
        "keywords": ["culture", "entertainment", "movie", "film", "music", "art", "book", "tv", "celebrity", "food", "travel"],
        "sort_order": 110,
    },
    {
        "key": "general",
        "label": "General",
        "icon": "newspaper",
        "keywords": [],
        "sort_order": 999,
    },
]


def seed_all(db: Session, household_id: int) -> None:
    """Idempotently ensures all default categories exist for the household."""
    existing = {
        c.key: c
        for c in db.query(Category).filter(Category.household_id == household_id).all()
    }

    for spec in DEFAULT_CATEGORIES:
        key = spec["key"]
        if key not in existing:
            cat = Category(
                household_id=household_id,
                key=key,
                label=spec["label"],
                icon=spec["icon"],
                sort_order=spec["sort_order"],
                hidden=0,
            )
            cat.keywords = spec["keywords"]
            db.add(cat)
    db.commit()


def seed_all_households(db: Session) -> None:
    """Seeds default categories for all households on the server."""
    households = db.query(Household.id).all()
    for (hid,) in households:
        seed_all(db, hid)


def get_general_category(db: Session, household_id: int) -> Category:
    """Returns the protected General fallback category for the household, creating it if needed."""
    cat = (
        db.query(Category)
        .filter(Category.household_id == household_id, Category.key == "general")
        .first()
    )
    if cat is None:
        cat = Category(
            household_id=household_id,
            key="general",
            label="General",
            icon="newspaper",
            sort_order=999,
            hidden=0,
        )
        cat.keywords = []
        db.add(cat)
        db.commit()
        db.refresh(cat)
    return cat


def keyword_categorize(
    title: str,
    summary: Optional[str],
    feed_tags: list[str],
    categories: list[Category],
    general_id: int,
) -> int:
    """
    Categorizes an article using keyword matching.
    Feed tags weigh 3x, title & summary words weigh 1x.
    Highest score >= 2 wins; otherwise falls back to General.
    """
    text_corpus = f"{title} {summary or ''}".lower()
    tag_corpus = " ".join(feed_tags).lower()

    best_id = general_id
    best_score = 0

    for cat in categories:
        if cat.id == general_id or cat.key == "general":
            continue
        keywords = cat.keywords
        if not keywords:
            continue

        score = 0
        for kw in keywords:
            kw_clean = kw.lower().strip()
            if not kw_clean:
                continue
            pattern = r"\b" + re.escape(kw_clean) + r"\b"
            if re.search(pattern, tag_corpus):
                score += 3
            if re.search(pattern, text_corpus):
                score += 1

        if score >= 2 and score > best_score:
            best_score = score
            best_id = cat.id

    return best_id
