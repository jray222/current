from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Household(Base):
    """
    The people who were invited together. Decks are shared by the whole server;
    progress belongs to each person.
    """
    __tablename__ = "households"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    users = relationship("User", back_populates="household", cascade="all, delete-orphan")
