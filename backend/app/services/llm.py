"""Batch AI categorization of news articles using Claude (Anthropic API).

When household.ai_categorize == 1 and an Anthropic API key is configured,
Current batches newly discovered articles and asks Claude to assign the most
accurate category using structured tool calling (assign_categories).
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.household import Household
from app.models.news import Article, Category
from app.services import ai as ai_service
from app.services import job_queue
from app.services.categories import get_general_category

logger = logging.getLogger(__name__)


class LlmError(RuntimeError):
    """The model call failed or returned something unusable; the message is safe to show."""


@dataclass
class LlmConfig:
    api_key: str
    model: str


def configured(db: Session) -> Optional[LlmConfig]:
    """Returns the effective LLM configuration if an API key is available."""
    effective = ai_service.runtime_settings(db)
    key = effective["anthropic_api_key"]
    return LlmConfig(key, effective["anthropic_model"]) if key else None


def make_client(api_key: str):
    """The Anthropic SDK client. Isolated so tests can swap in a mock (zero network in tests)."""
    import anthropic
    return anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)


CATEGORIZE_TOOL = {
    "name": "assign_categories",
    "description": "Assign editorial categories to a batch of news articles.",
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "description": "Category assignment for each article.",
                "items": {
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "integer",
                            "description": "The integer ID of the article being categorized",
                        },
                        "category_key": {
                            "type": "string",
                            "description": "The exact key of the chosen category (e.g. tech, world, politics, business, science, sports, culture, health, local, general)",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Brief 1-sentence rationale for the categorization choice",
                        },
                    },
                    "required": ["article_id", "category_key"],
                },
            }
        },
        "required": ["assignments"],
    },
}

CATEGORIZE_SYSTEM = (
    "You are an expert news editor and classifier for Current, an intelligent news reading app. "
    "Given a list of available categories (with keys and labels) and a list of articles "
    "(with article_id, title, summary, and tags), pick the most accurate category "
    "for each article. Prefer specific categories (tech, science, politics, business, health, sports, culture, world, us) "
    "over 'general' or 'top-stories' unless the article is broadly uncategorizable. "
    "Always invoke the assign_categories tool with assignments for each article provided."
)


def categorize_batch(cfg: LlmConfig, articles: list[dict], categories: list[dict]) -> list[dict]:
    """Calls Claude with structured tool calling to classify a batch of articles into categories.

    articles: list of dicts with keys: article_id (int), title (str), summary (optional str), tags (optional list)
    categories: list of dicts with keys: key (str), label (str)
    returns: list of dicts with keys: article_id (int), category_key (str)
    """
    if not articles or not categories:
        return []

    cat_list_str = "\n".join(f"- {c['key']}: {c['label']}" for c in categories)
    art_payload = []
    for a in articles:
        art_id = a.get("article_id") or a.get("id")
        title = a.get("title", "")
        summary = (a.get("summary") or "")[:250]
        tags = a.get("tags") or []
        art_payload.append({
            "article_id": art_id,
            "title": title,
            "summary": summary,
            "tags": tags[:5] if isinstance(tags, list) else [],
        })

    prompt = (
        f"Available categories:\n{cat_list_str}\n\n"
        f"Articles to categorize:\n{json.dumps(art_payload, indent=2)}\n\n"
        "Assign the best category to each article by calling assign_categories."
    )

    try:
        client = make_client(cfg.api_key)
        message = client.messages.create(
            model=cfg.model,
            max_tokens=4096,
            system=CATEGORIZE_SYSTEM,
            tools=[CATEGORIZE_TOOL],
            tool_choice={"type": "tool", "name": "assign_categories"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        raise LlmError(_anthropic_message(e) or f"Claude could not categorize articles ({type(e).__name__}).") from e

    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", "") == "tool_use" and block.name == "assign_categories":
            tool_input = getattr(block, "input", {})
            if isinstance(tool_input, dict) and "assignments" in tool_input:
                assignments = tool_input["assignments"]
                if isinstance(assignments, list):
                    return assignments

    raise LlmError("Claude did not return category assignments.")


def apply_ai_categorization(
    db: Session,
    household_id: int,
    article_ids: Optional[list[int]] = None,
    batch_size: int = 20,
) -> int:
    """Categorizes unassigned or specified articles for a household using Claude.

    Returns the number of articles successfully categorized.
    """
    cfg = configured(db)
    if not cfg:
        return 0

    household = db.get(Household, household_id)
    if not household or not household.ai_categorize:
        return 0

    # Query all active categories for this household
    cats = db.query(Category).filter(Category.household_id == household_id, Category.hidden == 0).all()
    if not cats:
        return 0

    cat_map = {c.key: c.id for c in cats}
    cat_specs = [{"key": c.key, "label": c.label} for c in cats]

    # Find articles to categorize
    if article_ids:
        articles = (
            db.query(Article)
            .filter(Article.household_id == household_id, Article.id.in_(article_ids))
            .all()
        )
    else:
        # Default: batch categorize articles in General
        general_cat = get_general_category(db, household_id)
        articles = (
            db.query(Article)
            .filter(Article.household_id == household_id, Article.category_id == general_cat.id)
            .order_by(Article.discovered_at.desc())
            .limit(50)
            .all()
        )

    if not articles:
        return 0

    updated_count = 0
    # Process in batches
    for i in range(0, len(articles), batch_size):
        chunk = articles[i : i + batch_size]
        payload = [
            {
                "article_id": a.id,
                "title": a.title,
                "summary": a.summary or "",
                "tags": a.feed_tags or [],
            }
            for a in chunk
        ]

        try:
            assignments = categorize_batch(cfg, payload, cat_specs)
        except Exception as e:
            logger.warning("AI categorization batch failed: %s", e)
            continue

        chunk_by_id = {a.id: a for a in chunk}
        for assign in assignments:
            if not isinstance(assign, dict):
                continue
            art_id = assign.get("article_id")
            cat_key = assign.get("category_key")
            if art_id in chunk_by_id and cat_key in cat_map:
                art = chunk_by_id[art_id]
                new_cat_id = cat_map[cat_key]
                if art.category_id != new_cat_id:
                    art.category_id = new_cat_id
                    updated_count += 1

        db.commit()

    return updated_count


def _ai_categorize_job(household_id: int, article_ids: list[int]) -> None:
    """Background worker handler for batch AI categorization."""
    with SessionLocal() as db:
        apply_ai_categorization(db, household_id, article_ids)


def _anthropic_message(e: Exception) -> str:
    """Extracts Anthropic's descriptive error message when available."""
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


# Register background job
job_queue.register("ai_categorize_batch", _ai_categorize_job)
