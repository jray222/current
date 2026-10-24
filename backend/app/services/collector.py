"""Collecting a deck's knowledge and pictures (job kind "collect").

For every card: the first paragraph of its Wikipedia article, then for every facet
a set of candidate pictures from Wikimedia Commons (search queries from the pack),
the article's lead picture (first facet) and iNaturalist's taxon photos (facets
with inat). Candidates are scored (`score`), the best few are kept, and the best
one is chosen and downloaded. A picture a person picked is never replaced, and a
hidden one never comes back.

Runs on the single job worker; progress is written to the deck as it goes.
"""
import io
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Card, CardImage, Deck
from app.services import job_queue, sources
from app.services.packs import card_search_name, facet_queries

# Titles with these words are diagrams, maps, herbarium sheets, stamps...: not what you see outdoors.
AVOID_WORDS = (
    "herbarium", "specimen", "map", "range", "distribution", "drawing", "illustration", "plate", "botanical",
    "sketch", "diagram", "logo", "stamp", "coin", "icon", "chart", "label", "sign", "microscop", "section",
    "köhler", "kohler", "britton", "lithograph", "engraving", "scan", "page", "book",
)
GOOD_CATEGORIES = ("quality images", "featured pictures", "valued images")

# Seconds between requests to the same service, to stay polite.
PAUSE = 0.15


def _utcnow():
    return datetime.now(timezone.utc)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", (text or "").lower()))


def score(candidate: dict, facet: dict, card: Card, *, lead: bool = False) -> float:
    """Higher is better. Below zero means it is probably not a photo of this facet."""
    title = (candidate.get("title") or "").lower()
    text = f"{title} {candidate.get('description', '')}"
    words = _words(text)
    s = 0.0

    must = [m.lower() for m in facet.get("must") or []]
    if must:
        if any(m in words for m in must):
            s += 5
        else:
            s -= 2

    name_words = _words(card_search_name(card)) | _words(card.name)
    name_words -= {"the", "of", "and", "common", "american", "eastern", "northern"}
    if name_words and name_words & words:
        s += 2 + len(name_words & words) * 0.5

    if any(w in text for w in AVOID_WORDS):
        s -= 9

    cats = candidate.get("categories") or ""
    if any(c in cats for c in GOOD_CATEGORIES):
        s += 2

    w, h = candidate.get("width") or 0, candidate.get("height") or 0
    if min(w, h) < 500:
        s -= 4
    elif min(w, h) >= 1200:
        s += 1

    s += max(0, 6 - (candidate.get("search_rank") or 0)) * 0.25
    if lead:
        s += 4
    if candidate.get("provider") == "inaturalist":
        s += 1.5 if facet.get("inat") else 0
    return round(s, 2)


def gather(client, deck: Deck, card: Card, facet: dict, first_facet: bool,
           queries: Optional[list[str]] = None) -> list[dict]:
    """Scored candidates for one facet of one card, best first, at most CANDIDATES_PER_FACET.

    With `queries` (a person's own search), only those are searched on Commons.
    """
    found: dict[tuple[str, str], dict] = {}

    def add(c: dict, lead: bool = False):
        key = (c["provider"], c["source_id"])
        c = {**c, "score": score(c, facet, card, lead=lead)}
        if key not in found or found[key]["score"] < c["score"]:
            found[key] = c

    if queries:
        for query in queries:
            for c in sources.commons_search(client, query):
                add(c)
            time.sleep(PAUSE)
        return sorted(found.values(), key=lambda c: -c["score"])[: settings.CANDIDATES_PER_FACET]
    if first_facet and card.wiki_title:
        lead_file = sources.wikipedia_lead_image(client, card.wiki_title)
        time.sleep(PAUSE)
        if lead_file:
            for c in sources.commons_files(client, [lead_file]):
                add(c, lead=True)
            time.sleep(PAUSE)
    for query in facet_queries(deck, card, facet)[:3]:
        for c in sources.commons_search(client, query):
            add(c)
        time.sleep(PAUSE)
    if facet.get("inat") and card.subtitle:
        for c in sources.inat_taxon_photos(client, card_search_name(card)):
            add(c)
        time.sleep(PAUSE)

    ranked = sorted(found.values(), key=lambda c: -c["score"])
    return ranked[: settings.CANDIDATES_PER_FACET]


# ------------------------------------------------------------------ files

def _card_dir(deck: Deck, card: Card) -> Path:
    return settings.images_dir / deck.slug / card.slug


def save_image(data: bytes, deck: Deck, card: Card, image: CardImage) -> None:
    """Writes a resized JPEG and a thumbnail; sets local_path and thumb_path (relative to IMAGES_DIR)."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception as e:  # not an image we can read
        raise sources.SourceError("The picture couldn't be read.") from e
    folder = _card_dir(deck, card)
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{image.facet}-{image.id}"
    big = img.copy()
    big.thumbnail((settings.IMAGE_MAX_PX, settings.IMAGE_MAX_PX))
    big.save(folder / f"{stem}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
    small = img.copy()
    small.thumbnail((settings.THUMB_MAX_PX, settings.THUMB_MAX_PX))
    small.save(folder / f"{stem}-thumb.jpg", "JPEG", quality=78, optimize=True)
    image.local_path = f"{deck.slug}/{card.slug}/{stem}.jpg"
    image.thumb_path = f"{deck.slug}/{card.slug}/{stem}-thumb.jpg"
    if not image.width or not image.height:
        image.width, image.height = img.size


def ensure_downloaded(db: Session, client, image: CardImage) -> None:
    if image.local_path and (settings.images_dir / image.local_path).is_file():
        return
    card = image.card
    data = sources.download(client, image.remote_url)
    save_image(data, card.deck, card, image)
    db.flush()


def remove_files(image: CardImage) -> None:
    for rel in (image.local_path, image.thumb_path):
        if rel:
            try:
                (settings.images_dir / rel).unlink(missing_ok=True)
            except OSError:
                pass
    image.local_path = image.thumb_path = None


# ------------------------------------------------------------------ choosing

def chosen(card: Card, facet_key: str) -> Optional[CardImage]:
    return next((i for i in card.images if i.facet == facet_key and i.status == "chosen"), None)


def choose(db: Session, client, card: Card, facet_key: str, image: Optional[CardImage] = None,
           by_person: bool = False) -> Optional[CardImage]:
    """Makes `image` (or the best candidate that downloads) the facet's picture."""
    options = [image] if image else sorted(
        (i for i in card.images if i.facet == facet_key and i.status == "candidate"), key=lambda i: -i.score)
    for option in options:
        try:
            ensure_downloaded(db, client, option)
        except sources.SourceError:
            if image:
                raise
            continue
        for other in card.images:
            if other.facet == facet_key and other.status == "chosen" and other is not option:
                other.status = "candidate"
                other.picked_by_person = 0
        option.status = "chosen"
        option.picked_by_person = 1 if by_person else 0
        db.flush()
        return option
    return None


_COPIED_FIELDS = ("page_url", "remote_url", "preview_url", "width", "height", "title", "author",
                  "license", "license_url")


def _store(db: Session, card: Card, key: str, candidates: list[dict]) -> list[CardImage]:
    """Adds (or refreshes) candidate rows for one facet. Returns them in the candidates' order."""
    existing = {(i.provider, i.source_id): i for i in card.images if i.facet == key}
    rows = []
    for rank, c in enumerate(candidates):
        row = existing.get((c["provider"], c["source_id"][:300]))
        if row is None:
            row = CardImage(card=card, facet=key, provider=c["provider"], source_id=c["source_id"][:300],
                            remote_url=c["remote_url"])
            db.add(row)
        for field in _COPIED_FIELDS:
            value = c.get(field)
            setattr(row, field, value[:800] if isinstance(value, str) else value)
        row.score, row.rank = c["score"], rank
        rows.append(row)
    db.flush()
    db.refresh(card)
    return rows


def search_card(db: Session, client, card: Card, facet_key: str, query: str) -> list[CardImage]:
    """A person's own Commons search for one view of a card. The results become candidates for that
    view; the view's picture only changes if it had none."""
    deck = card.deck
    facet = next(f for f in deck.facets or [] if f["key"] == facet_key)
    rows = _store(db, card, facet_key, gather(client, deck, card, facet, first_facet=False, queries=[query]))
    if chosen(card, facet_key) is None:
        choose(db, client, card, facet_key)
    db.commit()
    return rows


def assign(db: Session, client, image: CardImage, facet_key: str) -> CardImage:
    """A person puts this picture on a view of its card, even one it was found for another view of
    (a bark close-up that turned up in the leaf search). Returns the view's picture."""
    card = image.card
    target = image
    if image.facet != facet_key:
        target = next((i for i in card.images if i.facet == facet_key and i.provider == image.provider
                       and i.source_id == image.source_id), None)
        if target is None:
            target = CardImage(card=card, facet=facet_key, provider=image.provider, source_id=image.source_id,
                               score=image.score, rank=image.rank)
            for field in _COPIED_FIELDS:
                setattr(target, field, getattr(image, field))
            db.add(target)
            db.flush()
        if not target.local_path and image.local_path and (settings.images_dir / image.local_path).is_file():
            # Already downloaded for the other view: copy it rather than fetch it again.
            save_image((settings.images_dir / image.local_path).read_bytes(), card.deck, card, target)
    if target.status == "hidden":
        target.status = "candidate"
    choose(db, client, card, facet_key, target, by_person=True)
    return target


def collect_card(db: Session, client, deck: Deck, card: Card, force: bool = False,
                 only: Optional[str] = None) -> list[str]:
    """Fills one card (or only its `only` view). Returns problems worth reporting (empty when all went well)."""
    problems: list[str] = []
    if card.wiki_title and (force or not card.wiki_extract):
        try:
            summary = sources.wikipedia_summary(client, card.wiki_title)
            if summary:
                card.wiki_extract = summary["extract"]
                card.wiki_url = summary["url"]
            time.sleep(PAUSE)
        except sources.SourceError as e:
            problems.append(str(e))

    for n, facet in enumerate(deck.facets or []):
        key = facet["key"]
        if only and key != only:
            continue
        current = chosen(card, key)
        if current and (current.picked_by_person or not force) and current.local_path:
            continue
        try:
            candidates = gather(client, deck, card, facet, first_facet=(n == 0))
        except sources.SourceError as e:
            problems.append(str(e))
            continue
        _store(db, card, key, candidates)
        current = chosen(card, key)
        if current is None or (not current.picked_by_person and force):
            best = choose(db, client, card, key)
            if best is None and candidates:
                problems.append(f"No picture of {card.name} ({facet['label'].lower()}) could be downloaded.")
            elif not candidates:
                problems.append(f"No openly licensed picture found for {card.name} ({facet['label'].lower()}).")
        elif not current.local_path:
            choose(db, client, card, key, current, by_person=bool(current.picked_by_person))
    db.commit()
    return problems


def run_deck(deck_id: int, force: bool = False) -> None:
    """The job: collects every card of a deck, recording progress on the deck."""
    with SessionLocal() as db:
        deck = db.get(Deck, deck_id)
        if deck is None:
            return
        cards = list(deck.cards)
        deck.collect_status, deck.collect_done, deck.collect_total = "running", 0, len(cards)
        deck.collect_message = None
        db.commit()
        problems: list[str] = []
        failures_in_a_row = 0
        with sources.make_client() as client:
            for card in cards:
                try:
                    card_problems = collect_card(db, client, deck, card, force=force)
                except Exception as e:  # one bad card must not stop the deck
                    db.rollback()
                    card_problems = [f"{card.name}: {type(e).__name__}"]
                problems += card_problems
                unreachable = any(p.startswith("Couldn't reach") for p in card_problems)
                failures_in_a_row = failures_in_a_row + 1 if unreachable else 0
                deck = db.get(Deck, deck_id)
                deck.collect_done += 1
                db.commit()
                if failures_in_a_row >= 3:
                    deck.collect_status = "error"
                    deck.collect_message = (f"{card_problems[0]} Check that this server can reach "
                                            "commons.wikimedia.org, en.wikipedia.org and api.inaturalist.org.")
                    db.commit()
                    return
        deck.collect_status = "done"
        deck.collected_at = _utcnow()
        deck.collect_message = _summarize(problems)
        db.commit()


def _summarize(problems: list[str]) -> Optional[str]:
    if not problems:
        return None
    unique = list(dict.fromkeys(problems))
    more = f" (and {len(unique) - 3} more)" if len(unique) > 3 else ""
    return ("; ".join(unique[:3]) + more)[:500]


def enqueue(db: Session, deck: Deck, force: bool = False) -> bool:
    deck.collect_status = "queued"
    deck.collect_message = None
    db.commit()
    return job_queue.enqueue("collect", deck.id, force)


def resume(db: Session) -> None:
    """At startup: decks that were collecting when the server stopped, and shipped decks never collected."""
    for deck in db.query(Deck).all():
        if deck.collect_status in ("queued", "running"):
            enqueue(db, deck)
        elif settings.AUTO_COLLECT and deck.collect_status == "idle" and deck.collected_at is None:
            enqueue(db, deck)


job_queue.register("collect", run_deck)
