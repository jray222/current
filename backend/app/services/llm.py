"""Calling Claude to draft a new deck from a topic. Optional: callers check `configured()` first;
without a key, decks come from shipped packs or a pasted pack."""
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.services import ai as ai_service


class LlmError(RuntimeError):
    """The model call failed or returned something unusable; the message is safe to show."""


@dataclass
class LlmConfig:
    api_key: str
    model: str


def configured(db: Session) -> Optional[LlmConfig]:
    effective = ai_service.runtime_settings(db)
    key = effective["anthropic_api_key"]
    return LlmConfig(key, effective["anthropic_model"]) if key else None


def make_client(api_key: str):
    """The Anthropic SDK client. A function of its own so tests can swap in a fake (no network in tests)."""
    import anthropic
    return anthropic.Anthropic(api_key=api_key, timeout=300.0, max_retries=1)


DECK_TOOL = {
    "name": "save_deck",
    "description": "Save a visual flashcard deck for one knowledge domain.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short deck title, e.g. 'Planets of the solar system'"},
            "subtitle": {"type": "string", "description": "One line: how many cards and what they cover"},
            "icon": {"type": "string", "description": "A lucide icon name that fits, e.g. trees, bird, bug, orbit, atom, flower-2, book-open, drama, landmark, fish, mountain"},
            "description": {"type": "string"},
            "facets": {
                "type": "array", "minItems": 1, "maxItems": 4,
                "description": "The 1-4 views every card shows, each a kind of photo that helps recognise the subject. The first is the overall look.",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "short lowercase id, e.g. overall, bark, wings"},
                        "label": {"type": "string", "description": "1-2 words shown on the card"},
                        "queries": {"type": "array", "items": {"type": "string"},
                                    "description": "1-3 Wikimedia Commons search templates using {search} for the subject, e.g. '{search} bark'"},
                        "must": {"type": "array", "items": {"type": "string"},
                                 "description": "Lowercase words a matching photo title usually contains, e.g. bark, trunk. Empty for the overall facet."},
                        "inat": {"type": "boolean", "description": "true only for living things on the overall facet (adds iNaturalist photos)"},
                    },
                    "required": ["key", "label", "queries"],
                },
            },
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "subtitle": {"type": "string", "description": "Scientific name, symbol, author or other second name"},
                        "group": {"type": "string", "description": "A family or kind to group by"},
                        "wiki": {"type": "string", "description": "Exact English Wikipedia article title"},
                        "search": {"type": "string", "description": "Best term to search photos of it on Wikimedia Commons (scientific name for living things)"},
                        "summary": {"type": "string", "description": "One memorable line, under 120 characters"},
                        "facts": {"type": "array", "items": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
                                  "description": "2-3 [label, short value] pairs"},
                        "cues": {"type": "object", "additionalProperties": {"type": "string"},
                                 "description": "For each facet key, what to notice in that photo (under 80 characters)"},
                    },
                    "required": ["name", "wiki", "summary", "cues"],
                },
            },
        },
        "required": ["title", "facets", "cards"],
    },
}

DECK_SYSTEM = (
    "You design visual flashcard decks for a personal learning app. Each card is one subject (a species, "
    "a planet, an element, a painting...) shown as a few photos with a one-line summary and short cues on "
    "what to notice, so the person builds a visual memory. Be accurate: only facts you are sure of. Pick "
    "subjects that have real photographs on Wikimedia Commons. Always answer by calling save_deck."
)


def draft_deck(cfg: LlmConfig, topic: str, count: int = 25, notes: str = "") -> dict:
    """Asks Claude for a deck pack about `topic`; returns the tool input dict (validate it as a PackSpec)."""
    prompt = (f"Topic: {topic}\nNumber of cards: about {count}\n"
              + (f"Notes from the learner: {notes}\n" if notes else "")
              + "Choose the most common or most important subjects first.")
    try:
        client = make_client(cfg.api_key)
        message = client.messages.create(
            model=cfg.model, max_tokens=16000, system=DECK_SYSTEM, tools=[DECK_TOOL],
            tool_choice={"type": "tool", "name": "save_deck"}, messages=[{"role": "user", "content": prompt}])
    except Exception as e:
        raise LlmError(_anthropic_message(e) or f"Claude could not draft the deck ({type(e).__name__}).") from e
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", "") == "tool_use" and isinstance(getattr(block, "input", None), dict):
            return block.input
    raise LlmError("Claude did not return a deck.")


def _anthropic_message(e: Exception) -> str:
    """Anthropic's own error message when there is one (a bad key, no credit...)."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        msg = (body.get("error") or {}).get("message")
        if msg:
            return f"Anthropic: {msg}"
    if isinstance(body, str):
        try:
            return f"Anthropic: {json.loads(body)['error']['message']}"
        except Exception:
            return ""
    return ""
