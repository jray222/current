from datetime import datetime, timedelta, timezone
from app.database import SessionLocal
from app.models.household import Household
from app.services.crawl_schedule import (
    parse_time_to_minutes,
    times_of_day,
    should_crawl_household,
    due,
)


def test_time_parsing_and_schedules():
    assert parse_time_to_minutes("06:00") == 360
    assert parse_time_to_minutes("14:30") == 870
    assert parse_time_to_minutes("invalid") == 360

    # Every 4 hours starting at 6:00
    times = times_of_day(360, 4)
    assert len(times) == 6
    assert 360 in times  # 06:00
    assert 600 in times  # 10:00

    # Every 24 hours
    times24 = times_of_day(360, 24)
    assert len(times24) == 1
    assert times24[0] == 360


def test_should_crawl_household():
    now = datetime(2026, 11, 10, 8, 0, 0)

    # Disabled
    h_disabled = Household(crawl_enabled=0)
    assert not should_crawl_household(h_disabled, now)

    # Enabled, never handled
    h_new = Household(crawl_enabled=1, crawl_time="06:00", crawl_every_hours=24, crawl_handled_at=None)
    assert should_crawl_household(h_new, now)

    # Handled recently (1 hour ago)
    h_recent = Household(
        crawl_enabled=1,
        crawl_time="06:00",
        crawl_every_hours=24,
        crawl_handled_at=now - timedelta(hours=1),
    )
    assert not should_crawl_household(h_recent, now)


def test_due_households(make_user):
    client, user = make_user("schedule_user")

    with SessionLocal() as db:
        h = db.get(Household, user["household_id"])
        h.crawl_enabled = 1
        h.crawl_time = "06:00"
        h.crawl_every_hours = 24
        h.crawl_handled_at = None
        db.commit()

        now = datetime(2026, 11, 10, 8, 0, 0)
        due_list = due(db, now=now)
        assert user["household_id"] in due_list

        # Second check should not be due since handled_at was marked
        due_again = due(db, now=now)
        assert user["household_id"] not in due_again
