import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    icon = Column(String(50), default="newspaper", nullable=False)
    keywords_raw = Column("keywords", Text, default="[]", nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    hidden = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("household_id", "key", name="uq_categories_household_key"),
    )

    household = relationship("Household", back_populates="categories")
    articles = relationship("Article", back_populates="category")
    sources = relationship("Source", back_populates="category")

    @property
    def keywords(self) -> list[str]:
        try:
            return json.loads(self.keywords_raw or "[]")
        except Exception:
            return []

    @keywords.setter
    def keywords(self, val: list[str]) -> None:
        self.keywords_raw = json.dumps(val or [])


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(1000), nullable=False)
    name = Column(String(200), nullable=False)
    site_host = Column(String(255), nullable=False, index=True)
    favicon_url = Column(String(1000), nullable=True)

    fetch_mode = Column(String(20), default="rss", nullable=False)  # rss | html | browser
    feed_url = Column(String(1000), nullable=True)
    listing_url = Column(String(1000), nullable=True)
    link_pattern = Column(String(500), nullable=True)
    link_selector = Column(String(500), nullable=True)

    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    fetch_pages = Column(Integer, default=1, nullable=False)  # 0 or 1
    enabled = Column(Integer, default=1, nullable=False)      # 0 or 1

    etag = Column(String(255), nullable=True)
    last_modified = Column(String(255), nullable=True)
    crawl_status = Column(String(20), default="idle", nullable=False)  # idle | queued | running | done | error
    last_crawl_at = Column(DateTime, nullable=True)
    last_new_count = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    fail_streak = Column(Integer, default=0, nullable=False)

    # Full-text grab settings
    text_when = Column(String(20), default="open", nullable=False)        # open | keep | crawl
    text_method = Column(String(20), default="auto", nullable=False)      # auto | http | browser
    text_block_ads = Column(Integer, default=1, nullable=False)          # 0 or 1
    text_last_method = Column(String(20), nullable=True)                 # http | amp | browser
    text_selector = Column(String(500), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("household_id", "site_host", "feed_url", "listing_url", name="uq_sources_feed_listing"),
    )

    household = relationship("Household", back_populates="sources")
    category = relationship("Category", back_populates="sources")
    articles = relationship("Article", back_populates="source", cascade="all, delete-orphan")
    crawl_runs = relationship("CrawlRun", back_populates="source", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)

    url = Column(String(1000), nullable=False)
    canonical_url = Column(String(1000), nullable=True)
    url_hash = Column(String(64), nullable=False)
    amp_url = Column(String(1000), nullable=True)
    story_id = Column(String(64), nullable=False, index=True)

    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    published_at = Column(DateTime, nullable=True)
    discovered_at = Column(DateTime, default=_utcnow, nullable=False, index=True)

    image_remote_url = Column(String(1000), nullable=True)
    thumb_path = Column(String(500), nullable=True)
    feed_tags_raw = Column("feed_tags", Text, default="[]", nullable=False)
    lang = Column(String(10), default="en", nullable=False)

    # Full text content and status
    text_blocks_raw = Column("text_blocks", Text, nullable=True)  # JSON: [{"t": "p", "x": "text"}]
    text_status = Column(String(20), default="none", nullable=False)  # none | queued | running | ok | partial | failed | blocked
    text_method = Column(String(20), nullable=True)                   # http | amp | browser
    text_pages = Column(Integer, default=0, nullable=False)
    word_count = Column(Integer, default=0, nullable=False)
    text_error = Column(Text, nullable=True)
    text_fetched_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("household_id", "url_hash", name="uq_articles_household_url"),
        Index("ix_articles_household_discovered", "household_id", "discovered_at"),
        Index("ix_articles_household_story", "household_id", "story_id"),
        Index("ix_articles_household_category", "household_id", "category_id"),
    )

    household = relationship("Household", back_populates="articles")
    source = relationship("Source", back_populates="articles")
    category = relationship("Category", back_populates="articles")
    votes = relationship("Vote", back_populates="article")

    @property
    def feed_tags(self) -> list[str]:
        try:
            return json.loads(self.feed_tags_raw or "[]")
        except Exception:
            return []

    @feed_tags.setter
    def feed_tags(self, val: list[str]) -> None:
        self.feed_tags_raw = json.dumps(val or [])

    @property
    def text_blocks(self) -> Optional[list[dict[str, Any]]]:
        if not self.text_blocks_raw:
            return None
        try:
            return json.loads(self.text_blocks_raw)
        except Exception:
            return None

    @text_blocks.setter
    def text_blocks(self, val: Optional[list[dict[str, Any]]]) -> None:
        self.text_blocks_raw = json.dumps(val) if val is not None else None


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger = Column(String(20), default="manual", nullable=False)  # schedule | manual | add
    mode_used = Column(String(20), nullable=True)
    status = Column(String(20), default="running", nullable=False)   # running | done | error
    started_at = Column(DateTime, default=_utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    found = Column(Integer, default=0, nullable=False)
    new = Column(Integer, default=0, nullable=False)
    skipped_robots = Column(Integer, default=0, nullable=False)
    message = Column(Text, nullable=True)

    source = relationship("Source", back_populates="crawl_runs")


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)
    story_id = Column(String(64), nullable=False, index=True)

    verdict = Column(String(20), nullable=False)  # keep | skip | open
    weight = Column(Float, default=1.0, nullable=False)
    features_raw = Column("features", Text, nullable=False)  # snapshot JSON
    feature_version = Column(Integer, default=1, nullable=False)
    kept_state = Column(String(20), default="unread", nullable=False)  # unread | read | removed

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_votes_user_article"),
    )

    user = relationship("User")
    article = relationship("Article", back_populates="votes")

    @property
    def features(self) -> dict[str, float]:
        try:
            return json.loads(self.features_raw or "{}")
        except Exception:
            return {}

    @features.setter
    def features(self, val: dict[str, float]) -> None:
        self.features_raw = json.dumps(val or {})


class InterestModel(Base):
    __tablename__ = "interest_models"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True)

    weights_raw = Column("weights", Text, default="{}", nullable=False)
    g2_raw = Column("g2", Text, default="{}", nullable=False)
    bias = Column(Float, default=0.0, nullable=False)
    bias_g2 = Column(Float, default=1.0, nullable=False)
    n_votes = Column(Integer, default=0, nullable=False)
    feature_version = Column(Integer, default=1, nullable=False)
    muted_raw = Column("muted", Text, default="[]", nullable=False)

    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User")

    @property
    def weights(self) -> dict[str, float]:
        try:
            return json.loads(self.weights_raw or "{}")
        except Exception:
            return {}

    @weights.setter
    def weights(self, val: dict[str, float]) -> None:
        self.weights_raw = json.dumps(val or {})

    @property
    def g2(self) -> dict[str, float]:
        try:
            return json.loads(self.g2_raw or "{}")
        except Exception:
            return {}

    @g2.setter
    def g2(self, val: dict[str, float]) -> None:
        self.g2_raw = json.dumps(val or {})

    @property
    def muted(self) -> list[str]:
        try:
            return json.loads(self.muted_raw or "[]")
        except Exception:
            return []

    @muted.setter
    def muted(self, val: list[str]) -> None:
        self.muted_raw = json.dumps(val or [])
