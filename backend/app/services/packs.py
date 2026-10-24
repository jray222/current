"""Deck packs: a deck described as JSON (app/packs/*.json, an import, or a Claude draft).

A pack names the deck, its facets and its cards. Pictures are not in the pack:
the collector finds them from each facet's search queries. Loading a pack again
updates the text of existing cards and adds new ones; pictures a person picked
and cards' progress are kept.

{
  "slug": "midwest-trees", "version": 1, "title": "...", "subtitle": "...", "icon": "trees",
  "description": "...",
  "facets": [{"key": "bark", "label": "Bark", "queries": ["{search} bark"], "must": ["bark"], "inat": false}],
  "cards": [{"name": "White oak", "subtitle": "Quercus alba", "group": "Oaks", "wiki": "Quercus alba",
             "search": "Quercus alba", "summary": "...", "facts": [["Height", "60-100 ft"]],
             "cues": {"bark": "..."}, "queries": {"fruit": ["Quercus alba acorns"]}}]
}

In queries, {search} is the card's search name (else its subtitle, else its name) and {name} its name.
"""
import json
import re
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models import Card, Deck

PACKS_DIR = Path(__file__).resolve().parent.parent / "packs"
MAX_CARDS = 300


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:80] or "deck"


class FacetSpec(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=40)
    queries: list[str] = Field(default_factory=lambda: ["{search}"], max_length=6)
    # Words a good picture's title usually contains ("bark"); others rank lower.
    must: list[str] = Field(default_factory=list, max_length=30)
    # Also take iNaturalist's photos of the taxon (living things only).
    inat: bool = False

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return slugify(v)


class CardSpec(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subtitle: Optional[str] = Field(default=None, max_length=200)
    group: Optional[str] = Field(default=None, max_length=80)
    wiki: Optional[str] = Field(default=None, max_length=200)
    search: Optional[str] = Field(default=None, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=400)
    facts: list[Union[list[str], dict]] = Field(default_factory=list, max_length=8)
    cues: dict[str, str] = Field(default_factory=dict)
    queries: dict[str, list[str]] = Field(default_factory=dict)


class PackSpec(BaseModel):
    slug: Optional[str] = Field(default=None, max_length=80)
    version: int = 1
    title: str = Field(min_length=1, max_length=120)
    subtitle: Optional[str] = Field(default=None, max_length=200)
    icon: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = Field(default=None, max_length=2000)
    facets: list[FacetSpec] = Field(min_length=1, max_length=8)
    cards: list[CardSpec] = Field(min_length=1, max_length=MAX_CARDS)


def _facts(raw: list) -> list[dict]:
    out = []
    for f in raw:
        if isinstance(f, dict):
            label, value = f.get("label"), f.get("value")
        elif isinstance(f, (list, tuple)) and len(f) == 2:
            label, value = f
        else:
            continue
        if label and value:
            out.append({"label": str(label)[:40], "value": str(value)[:160]})
    return out


def card_search_name(card: Card) -> str:
    return card.search_name or card.subtitle or card.name


def facet_queries(deck: Deck, card: Card, facet: dict) -> list[str]:
    """The search queries for one facet of a card: the card's own, then the deck's templates."""
    own = (card_extra_queries(card) or {}).get(facet["key"]) or []
    templates = facet.get("queries") or ["{search}"]
    search = card_search_name(card)
    filled = [t.replace("{search}", search).replace("{name}", card.name) for t in templates]
    seen, out = set(), []
    for q in [*own, *filled]:
        q = " ".join(q.split())
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def card_extra_queries(card: Card) -> dict:
    return (card.cues or {}).get("_queries") or {}


def apply_pack(db: Session, pack: PackSpec, source: str = "pack") -> Deck:
    """Creates or updates the deck from a pack. Returns the deck (flushed, not committed)."""
    slug = slugify(pack.slug or pack.title)
    deck = db.query(Deck).filter(Deck.slug == slug).first()
    if deck is None:
        deck = Deck(slug=slug, source=source)
        db.add(deck)
    deck.title = pack.title
    deck.subtitle = pack.subtitle
    deck.icon = pack.icon
    deck.description = pack.description
    deck.facets = [f.model_dump() for f in pack.facets]
    deck.pack_version = pack.version
    db.flush()

    existing = {c.slug: c for c in db.query(Card).filter(Card.deck_id == deck.id)}
    for order, spec in enumerate(pack.cards):
        cslug = slugify(spec.name)
        card = existing.get(cslug)
        if card is None:
            card = Card(deck_id=deck.id, slug=cslug)
            db.add(card)
            existing[cslug] = card
        card.name = spec.name
        card.subtitle = spec.subtitle
        card.group = spec.group
        card.summary = spec.summary
        card.facts = _facts(spec.facts)
        cues = {k: v[:200] for k, v in spec.cues.items() if isinstance(v, str)}
        if spec.queries:
            cues["_queries"] = {k: [q[:200] for q in v[:4]] for k, v in spec.queries.items()}
        card.cues = cues
        card.search_name = spec.search
        if spec.wiki and spec.wiki != card.wiki_title:
            card.wiki_title = spec.wiki
            card.wiki_extract = None
        card.sort_order = order
    db.flush()
    return deck


def load_file(path: Path) -> PackSpec:
    return PackSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))


def shipped_packs() -> list[PackSpec]:
    return [load_file(p) for p in sorted(PACKS_DIR.glob("*.json"))]


def seed_shipped(db: Session) -> list[Deck]:
    """Adds shipped decks that are missing and updates those whose pack version went up."""
    changed = []
    for pack in shipped_packs():
        slug = slugify(pack.slug or pack.title)
        deck = db.query(Deck).filter(Deck.slug == slug).first()
        if deck is None or (deck.source == "pack" and pack.version > (deck.pack_version or 0)):
            changed.append(apply_pack(db, pack, source="pack"))
    db.commit()
    return changed


def export_pack(deck: Deck) -> dict:
    """The deck as a pack, to share or edit and import again."""
    cards = []
    for c in deck.cards:
        cues = dict(c.cues or {})
        queries = cues.pop("_queries", None)
        entry = {"name": c.name, "subtitle": c.subtitle, "group": c.group, "wiki": c.wiki_title,
                 "search": c.search_name, "summary": c.summary,
                 "facts": [[f["label"], f["value"]] for f in c.facts or []], "cues": cues}
        if queries:
            entry["queries"] = queries
        cards.append({k: v for k, v in entry.items() if v not in (None, "", [], {})})
    return {"slug": deck.slug, "version": deck.pack_version, "title": deck.title, "subtitle": deck.subtitle,
            "icon": deck.icon, "description": deck.description, "facets": deck.facets, "cards": cards}
