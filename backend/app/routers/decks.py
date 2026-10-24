"""Decks, cards, pictures and review progress.

Decks are shared by everyone on this server; reading them needs a sign-in, and
changing them (collecting, choosing pictures, adding or removing decks) is for
the instance owner. Progress is per person.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_superuser, get_current_user
from app.models import Card, CardImage, Deck, User
from app.services import collector, llm, packs, progress, sources

router = APIRouter(prefix="/api/v1", tags=["Decks"])


# ------------------------------------------------------------------ helpers

def _deck_or_404(db: Session, slug: str) -> Deck:
    deck = db.query(Deck).filter(Deck.slug == slug).first()
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


def _image_or_404(db: Session, image_id: int) -> CardImage:
    image = db.get(CardImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Picture not found")
    return image


def _image_json(i: CardImage) -> dict:
    return {"id": i.id, "facet": i.facet, "status": i.status, "provider": i.provider, "title": i.title,
            "author": i.author, "license": i.license, "license_url": i.license_url, "page_url": i.page_url,
            "width": i.width, "height": i.height, "downloaded": bool(i.local_path),
            "picked_by_person": bool(i.picked_by_person), "score": i.score}


def _facets(deck: Deck) -> list[dict]:
    return [{"key": f["key"], "label": f["label"]} for f in deck.facets or []]


def _cover(deck: Deck) -> Optional[int]:
    """The first card's first-facet picture, else any picture."""
    first = (deck.facets or [{}])[0].get("key")
    fallback = None
    for card in deck.cards:
        for i in card.images:
            if i.status == "chosen" and i.local_path:
                if i.facet == first:
                    return i.id
                fallback = fallback or i.id
        if fallback:
            return fallback
    return fallback


def _deck_summary(db: Session, deck: Deck, user: User) -> dict:
    card_ids = [c.id for c in deck.cards]
    rows = progress.for_user(db, user.id, card_ids)
    return {
        "slug": deck.slug, "title": deck.title, "subtitle": deck.subtitle, "icon": deck.icon,
        "description": deck.description, "source": deck.source, "facets": _facets(deck),
        "card_count": len(card_ids), "cover_image_id": _cover(deck),
        "collect": {"status": deck.collect_status, "done": deck.collect_done, "total": deck.collect_total,
                    "message": deck.collect_message,
                    "collected_at": deck.collected_at.isoformat() if deck.collected_at else None},
        "progress": progress.summary(rows, len(card_ids)),
    }


def _card_json(card: Card, row) -> dict:
    cues = {k: v for k, v in (card.cues or {}).items() if not k.startswith("_")}
    images = {i.facet: _image_json(i) for i in card.images if i.status == "chosen" and i.local_path}
    return {
        "id": card.id, "slug": card.slug, "name": card.name, "subtitle": card.subtitle, "group": card.group,
        "summary": card.summary, "facts": card.facts or [], "cues": cues, "wiki_url": card.wiki_url,
        "wiki_extract": card.wiki_extract, "images": images,
        "progress": {"box": row.box, "seen": row.seen, "knew": row.knew} if row else {"box": 0, "seen": 0, "knew": 0},
    }


# ------------------------------------------------------------------ reading

@router.get("/decks")
def list_decks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_deck_summary(db, d, user) for d in db.query(Deck).order_by(Deck.id)]


@router.get("/today")
def today(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The deck of the day: a different one each day."""
    day = progress.local_today()
    deck = progress.deck_of_the_day(db, day)
    return {"date": day.isoformat(), "deck": _deck_summary(db, deck, user) if deck else None}


# Before /decks/{slug}, which would otherwise take "template" for a slug.
@router.get("/decks/template")
def deck_template(_user: User = Depends(get_current_user)):
    """A small example pack with every field filled in, to start a deck of your own from."""
    return packs.template()


@router.get("/decks/{slug}")
def get_deck(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deck = _deck_or_404(db, slug)
    rows = progress.for_user(db, user.id, [c.id for c in deck.cards])
    return {**_deck_summary(db, deck, user), "cards": [_card_json(c, rows.get(c.id)) for c in deck.cards]}


@router.get("/decks/{slug}/quiz")
def quiz(slug: str, limit: int = Query(20, ge=1, le=300), db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """Card ids to quiz on, in order: due first, then new, then the rest."""
    deck = _deck_or_404(db, slug)
    cards = [c for c in deck.cards if any(i.status == "chosen" and i.local_path for i in c.images)]
    rows = progress.for_user(db, user.id, [c.id for c in cards])
    return {"card_ids": progress.quiz_order(cards, rows, limit)}


@router.get("/images/{image_id}/file")
def image_file(image_id: int, size: Literal["full", "thumb"] = "full", db: Session = Depends(get_db),
               _user: User = Depends(get_current_user)):
    image = _image_or_404(db, image_id)
    rel = image.thumb_path if size == "thumb" else image.local_path
    if not rel:
        raise HTTPException(status_code=404, detail="Picture not downloaded yet")
    root = settings.images_dir.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Picture not found")
    # File names carry the picture's id, so a given URL never changes content.
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=2592000, immutable"})


# ------------------------------------------------------------------ progress

class ProgressIn(BaseModel):
    card_id: int
    result: Literal["seen", "knew", "again"]


@router.post("/progress")
def record_progress(payload: ProgressIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Card, payload.card_id) is None:
        raise HTTPException(status_code=404, detail="Card not found")
    row = progress.record(db, user.id, payload.card_id, payload.result)
    return {"card_id": row.card_id, "box": row.box, "seen": row.seen, "knew": row.knew,
            "due_at": row.due_at.isoformat() if row.due_at else None}


# ------------------------------------------------------------------ owner: pictures

def _card_or_404(db: Session, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def _options(card: Card, facet: Optional[str] = None) -> list[dict]:
    return [{**_image_json(i), "preview_url": i.preview_url}
            for i in sorted(card.images, key=lambda i: (i.status != "chosen", -i.score))
            if facet is None or i.facet == facet]


def _facet_or_400(card: Card, facet: str) -> str:
    if facet not in {f["key"] for f in card.deck.facets or []}:
        raise HTTPException(status_code=400, detail="This deck has no such view")
    return facet


@router.get("/cards/{card_id}/images")
def card_images(card_id: int, facet: Optional[str] = None, db: Session = Depends(get_db),
                _user: User = Depends(get_current_superuser)):
    """Every picture found for a card (or one facet of it), to choose a better one."""
    return _options(_card_or_404(db, card_id), facet)


class CardCollectIn(BaseModel):
    # Only this view; every view when left out.
    facet: Optional[str] = Field(default=None, max_length=40)
    # Your own Commons search for that view, e.g. "white oak bark closeup".
    query: Optional[str] = Field(default=None, max_length=200)


@router.post("/cards/{card_id}/collect")
def collect_one_card(card_id: int, payload: CardCollectIn = CardCollectIn(), db: Session = Depends(get_db),
                     _user: User = Depends(get_current_superuser)):
    """Looks again for one card's pictures, now. Pictures you picked stay; with a query, the results
    are only added as candidates (the view keeps its picture unless it had none)."""
    card = _card_or_404(db, card_id)
    if card.deck.collect_status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="The deck is gathering pictures. Try again when it's done.")
    facet = _facet_or_400(card, payload.facet) if payload.facet else None
    query = " ".join((payload.query or "").split())
    if query and not facet:
        raise HTTPException(status_code=400, detail="Say which view to search for")
    found: list[int] = []
    problems: list[str] = []
    with sources.make_client() as client:
        if query:
            try:
                found = [i.id for i in collector.search_card(db, client, card, facet, query)]
            except sources.SourceError as e:
                db.rollback()
                raise HTTPException(status_code=502, detail=str(e))
            if not found:
                problems.append(f"Nothing openly licensed came up for “{query}”.")
        else:
            problems = collector.collect_card(db, client, card.deck, card, force=True, only=facet)
    db.refresh(card)
    return {"found": found, "problems": problems, "images": _options(card)}


class ChooseIn(BaseModel):
    # Put the picture on another view of its card (a bark photo found in the leaf search).
    facet: Optional[str] = Field(default=None, max_length=40)


@router.post("/images/{image_id}/choose")
def choose_image(image_id: int, payload: ChooseIn = ChooseIn(), db: Session = Depends(get_db),
                 _user: User = Depends(get_current_superuser)):
    image = _image_or_404(db, image_id)
    facet = _facet_or_400(image.card, payload.facet) if payload.facet else image.facet
    try:
        with sources.make_client() as client:
            image = collector.assign(db, client, image, facet)
    except sources.SourceError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(e))
    db.commit()
    return _image_json(image)


@router.post("/images/{image_id}/hide")
def hide_image(image_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_superuser)):
    """Never show this picture again; if it was the facet's picture, the next best takes its place."""
    image = _image_or_404(db, image_id)
    was_chosen = image.status == "chosen"
    image.status = "hidden"
    image.picked_by_person = 0
    collector.remove_files(image)
    db.flush()
    replacement = None
    if was_chosen:
        with sources.make_client() as client:
            replacement = collector.choose(db, client, image.card, image.facet)
    db.commit()
    return {"hidden": image.id, "replacement": _image_json(replacement) if replacement else None}


# ------------------------------------------------------------------ owner: decks

class CollectIn(BaseModel):
    # Also look again for facets that already have a picture (pictures you picked stay).
    force: bool = False


@router.post("/decks/{slug}/collect")
def collect(slug: str, payload: CollectIn = CollectIn(), db: Session = Depends(get_db),
            _user: User = Depends(get_current_superuser)):
    deck = _deck_or_404(db, slug)
    collector.enqueue(db, deck, force=payload.force)
    return {"status": deck.collect_status}


@router.get("/decks/{slug}/export")
def export_deck(slug: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return packs.export_pack(_deck_or_404(db, slug))


@router.post("/decks/import")
def import_deck(pack: dict, db: Session = Depends(get_db), _user: User = Depends(get_current_superuser)):
    """Adds (or updates) a deck from a pack, then starts collecting its pictures."""
    try:
        spec = packs.PackSpec.model_validate(pack)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        raise HTTPException(status_code=400, detail=f"That pack isn't valid: {where} {first.get('msg', '')}".strip())
    source = pack.get("_source") if pack.get("_source") in ("ai", "import") else "import"
    deck = packs.apply_pack(db, spec, source=source)
    db.commit()
    collector.enqueue(db, deck)
    return {"slug": deck.slug}


class DraftIn(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    count: int = Field(default=25, ge=5, le=80)
    notes: str = Field(default="", max_length=500)


@router.post("/decks/draft")
def draft_deck(payload: DraftIn, db: Session = Depends(get_db), _user: User = Depends(get_current_superuser)):
    """Claude drafts a pack for a topic. Nothing is saved: the owner reviews it, then imports it."""
    cfg = llm.configured(db)
    if cfg is None:
        raise HTTPException(status_code=400, detail="Add an Anthropic API key in Settings > AI to draft decks.")
    try:
        draft = llm.draft_deck(cfg, payload.topic, payload.count, payload.notes)
        spec = packs.PackSpec.model_validate({**draft, "slug": packs.slugify(draft.get("title") or payload.topic)})
    except llm.LlmError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValidationError:
        raise HTTPException(status_code=502, detail="Claude's draft was incomplete. Try again.")
    return {**spec.model_dump(exclude_none=True), "_source": "ai"}


@router.delete("/decks/{slug}")
def delete_deck(slug: str, db: Session = Depends(get_db), _user: User = Depends(get_current_superuser)):
    import shutil
    from app.models import CardProgress
    deck = _deck_or_404(db, slug)
    card_ids = [c.id for c in deck.cards]
    if card_ids:
        db.query(CardProgress).filter(CardProgress.card_id.in_(card_ids)).delete(synchronize_session=False)
    db.delete(deck)
    db.commit()
    folder = (settings.images_dir / slug).resolve()
    if folder.is_relative_to(settings.images_dir.resolve()) and folder != settings.images_dir.resolve():
        shutil.rmtree(folder, ignore_errors=True)
    return {"deleted": slug}
