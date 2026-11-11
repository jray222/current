from unittest.mock import MagicMock, patch
import pytest

from app.database import SessionLocal
from app.models.household import Household
from app.models.news import Article, Category, Source
from app.services import categories as category_service
from app.services import job_queue
from app.services import llm
from app.services.crawler import _ingest_entries
from app.services.feeds import FeedEntry


@pytest.fixture
def household():
    with SessionLocal() as db:
        h = Household(name="AI Test Household", ai_categorize=1)
        db.add(h)
        db.commit()
        db.refresh(h)
        category_service.seed_all(db, h.id)
        hid = h.id
    return hid


@pytest.fixture
def mock_anthropic():
    with patch("app.services.llm.make_client") as mock_make:
        client = MagicMock()
        mock_make.return_value = client
        yield client


def test_configured_returns_none_when_no_key():
    with SessionLocal() as db:
        assert llm.configured(db) is None


def test_configured_returns_config_when_key_present(monkeypatch):
    monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "sk-ant-test-key-123")
    with SessionLocal() as db:
        cfg = llm.configured(db)
        assert cfg is not None
        assert cfg.api_key == "sk-ant-test-key-123"


def test_categorize_batch_empty():
    cfg = llm.LlmConfig(api_key="test", model="claude-3-5-haiku-latest")
    assert llm.categorize_batch(cfg, [], [{"key": "tech", "label": "Tech"}]) == []
    assert llm.categorize_batch(cfg, [{"id": 1, "title": "Foo"}], []) == []


def test_categorize_batch_success(mock_anthropic):
    cfg = llm.LlmConfig(api_key="test", model="claude-3-5-haiku-latest")

    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.name = "assign_categories"
    mock_tool_use.input = {
        "assignments": [
            {"article_id": 101, "category_key": "tech"},
            {"article_id": 102, "category_key": "sports"},
        ]
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_use]
    mock_anthropic.messages.create.return_value = mock_response

    articles = [
        {"id": 101, "title": "New GPU announced with faster memory", "summary": "Nvidia unveils new architecture"},
        {"id": 102, "title": "Team wins championship in extra innings", "summary": "World series game 7 thriller"},
    ]
    categories = [
        {"key": "tech", "label": "Tech"},
        {"key": "sports", "label": "Sports"},
    ]

    assignments = llm.categorize_batch(cfg, articles, categories)
    assert len(assignments) == 2
    assert assignments[0]["article_id"] == 101
    assert assignments[0]["category_key"] == "tech"
    assert assignments[1]["article_id"] == 102
    assert assignments[1]["category_key"] == "sports"


def test_categorize_batch_handles_anthropic_error(mock_anthropic):
    cfg = llm.LlmConfig(api_key="test", model="claude-3-5-haiku-latest")
    mock_anthropic.messages.create.side_effect = RuntimeError("Rate limit exceeded")

    articles = [{"id": 101, "title": "Article 1"}]
    categories = [{"key": "tech", "label": "Tech"}]

    with pytest.raises(llm.LlmError) as exc_info:
        llm.categorize_batch(cfg, articles, categories)
    assert "could not categorize articles" in str(exc_info.value)


def test_apply_ai_categorization_when_disabled(household):
    with SessionLocal() as db:
        h = db.get(Household, household)
        h.ai_categorize = 0
        db.commit()

        count = llm.apply_ai_categorization(db, household)
        assert count == 0


def test_apply_ai_categorization_updates_article_categories(household, monkeypatch, mock_anthropic):
    monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "sk-ant-test-key")

    with SessionLocal() as db:
        gen_cat = category_service.get_general_category(db, household)
        tech_cat = db.query(Category).filter(Category.household_id == household, Category.key == "tech").first()
        tech_id = tech_cat.id

        src = Source(
            household_id=household,
            name="Tech Feed",
            url="https://tech.example.com",
            site_host="tech.example.com",
            fetch_mode="rss",
        )
        db.add(src)
        db.commit()

        art = Article(
            household_id=household,
            source_id=src.id,
            category_id=gen_cat.id,
            url="https://tech.example.com/ai-breakthrough",
            url_hash="tech-hash-1",
            story_id="test-story-1",
            title="Major AI breakthrough reported",
            summary="A new open source language model achieves state of the art results.",
        )
        db.add(art)
        db.commit()
        db.refresh(art)
        art_id = art.id

    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.name = "assign_categories"
    mock_tool_use.input = {
        "assignments": [
            {"article_id": art_id, "category_key": "tech"},
        ]
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_use]
    mock_anthropic.messages.create.return_value = mock_response

    with SessionLocal() as db:
        updated = llm.apply_ai_categorization(db, household, [art_id])
        assert updated == 1

        refreshed_art = db.get(Article, art_id)
        assert refreshed_art.category_id == tech_id


def test_crawler_enqueues_ai_categorization_when_enabled(household, monkeypatch):
    with SessionLocal() as db:
        source = Source(
            household_id=household,
            name="General Source",
            url="https://news.example.com",
            site_host="news.example.com",
            category_id=None,  # No fixed category
            fetch_mode="rss",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        entries = [
            FeedEntry(
                title="Tech advancement unveiled",
                url="https://news.example.com/tech-story",
                summary="Exciting new processors announced.",
                published_at=None,
                author="Jane Doe",
                tags=["technology"],
                image_remote_url=None,
            )
        ]

        enqueued_jobs = []

        def fake_enqueue(kind, *args, **kwargs):
            enqueued_jobs.append((kind, args, kwargs))
            return True

        monkeypatch.setattr(job_queue, "enqueue", fake_enqueue)

        found, new = _ingest_entries(db, source, entries)
        assert found == 1
        assert new == 1

        # Check that an ai_categorize_batch job was enqueued
        ai_jobs = [j for j in enqueued_jobs if j[0] == "ai_categorize_batch"]
        assert len(ai_jobs) == 1
        assert ai_jobs[0][1][0] == household
