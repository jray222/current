from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Household(Base):
    """
    A household tenancy group. News sources, categories and articles belong
    to a household; votes, interest learning and kept reading lists belong to each user.
    """
    __tablename__ = "households"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    # Crawl scheduling & categorization settings
    crawl_enabled = Column(Integer, default=1, nullable=False)
    crawl_time = Column(String(10), default="06:00", nullable=False)
    crawl_every_hours = Column(Integer, default=24, nullable=False)
    crawl_handled_at = Column(DateTime, nullable=True)
    ai_categorize = Column(Integer, default=0, nullable=False)

    users = relationship("User", back_populates="household", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="household", cascade="all, delete-orphan")
    sources = relationship("Source", back_populates="household", cascade="all, delete-orphan")
    articles = relationship("Article", back_populates="household", cascade="all, delete-orphan")
