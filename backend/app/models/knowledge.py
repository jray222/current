"""Decks of knowledge: one deck per domain (midwestern trees, planets, elements...).

A deck lists its facets: the views every card has (a tree's overall look, bark,
leaf and fruit; a planet's full disc and surface). Each card has one chosen
picture per facet, picked from candidates the collector found, with the
author and licence kept beside it. Decks are shared by everyone on the server;
how well each person knows a card is theirs alone (CardProgress).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Deck(Base):
    __tablename__ = "decks"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(80), unique=True, nullable=False, index=True)
    title = Column(String(120), nullable=False)
    subtitle = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    # lucide icon name for the deck tile, e.g. "trees", "orbit", "atom".
    icon = Column(String(40), nullable=True)
    # [{key, label, queries: [...], must: [...], inat: bool}] (see services/packs.py)
    facets = Column(JSON, nullable=False, default=list)
    # "pack" (shipped in app/packs), "ai" (drafted by Claude) or "import" (a pasted pack).
    source = Column(String(20), nullable=False, default="pack")
    pack_version = Column(Integer, nullable=False, default=1)

    # Collection of pictures and summaries (services/collector.py).
    collect_status = Column(String(20), nullable=False, default="idle")  # idle, queued, running, done, error
    collect_done = Column(Integer, nullable=False, default=0)
    collect_total = Column(Integer, nullable=False, default=0)
    collect_message = Column(String(500), nullable=True)
    collected_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    cards = relationship("Card", back_populates="deck", cascade="all, delete-orphan",
                         order_by="Card.sort_order")


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("deck_id", "slug", name="uq_card_slug"),)

    id = Column(Integer, primary_key=True, index=True)
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)
    slug = Column(String(120), nullable=False)
    name = Column(String(160), nullable=False)
    # A second name: the scientific name, a symbol, an author.
    subtitle = Column(String(200), nullable=True)
    # A family or kind to group by: "Oaks", "Gas giants", "Noble gases".
    group = Column(String(80), nullable=True)
    # One short line to remember it by.
    summary = Column(String(400), nullable=True)
    # [{label, value}], a few short facts.
    facts = Column(JSON, nullable=False, default=list)
    # {facet key: what to notice in that picture}
    cues = Column(JSON, nullable=False, default=dict)
    # The search term for pictures when it differs from the subtitle (e.g. "Acer saccharum").
    search_name = Column(String(200), nullable=True)
    wiki_title = Column(String(200), nullable=True)
    wiki_url = Column(String(500), nullable=True)
    # The first paragraph of the Wikipedia article (CC BY-SA), shown under "More".
    wiki_extract = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    deck = relationship("Deck", back_populates="cards")
    images = relationship("CardImage", back_populates="card", cascade="all, delete-orphan",
                          order_by="CardImage.rank")


class CardImage(Base):
    """A picture of one facet of a card. Status: candidate, chosen (one per facet) or hidden."""
    __tablename__ = "card_images"
    __table_args__ = (UniqueConstraint("card_id", "facet", "provider", "source_id", name="uq_card_image_source"),)

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False, index=True)
    facet = Column(String(40), nullable=False)
    status = Column(String(12), nullable=False, default="candidate")
    # Set when a person picked it, so a new collection never replaces it.
    picked_by_person = Column(Integer, nullable=False, default=0)
    score = Column(Float, nullable=False, default=0)
    rank = Column(Integer, nullable=False, default=0)

    provider = Column(String(20), nullable=False)  # commons, inaturalist, wikipedia
    source_id = Column(String(300), nullable=False)  # Commons file title, iNaturalist photo id
    page_url = Column(String(600), nullable=True)  # where the licence and author can be checked
    remote_url = Column(String(800), nullable=False)  # the sized file to download
    preview_url = Column(String(800), nullable=True)  # a small remote copy, for choosing among candidates
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    title = Column(String(400), nullable=True)
    author = Column(String(300), nullable=True)
    license = Column(String(60), nullable=True)  # "CC BY-SA 4.0", "CC0", "Public domain"
    license_url = Column(String(300), nullable=True)

    # Relative to IMAGES_DIR once downloaded (chosen pictures are downloaded; candidates on demand).
    local_path = Column(String(400), nullable=True)
    thumb_path = Column(String(400), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    card = relationship("Card", back_populates="images")


class CardProgress(Base):
    """How well one person knows one card: a Leitner box (0 new ... 5 known)."""
    __tablename__ = "card_progress"
    __table_args__ = (UniqueConstraint("user_id", "card_id", name="uq_progress_user_card"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False, index=True)
    box = Column(Integer, nullable=False, default=0)
    seen = Column(Integer, nullable=False, default=0)
    knew = Column(Integer, nullable=False, default=0)
    last_seen_at = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=True)
