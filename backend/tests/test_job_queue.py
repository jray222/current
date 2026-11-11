from app.services import job_queue
from app.services.job_queue import Priority


def test_priority_ordering():
    job_queue.clear()
    executed = []

    def task_high():
        executed.append("high")

    def task_normal():
        executed.append("normal")

    def task_low():
        executed.append("low")

    job_queue.register("high", task_high)
    job_queue.register("normal", task_normal)
    job_queue.register("low", task_low)

    # Queue normal first, then low, then high
    job_queue.enqueue("normal", priority=Priority.NORMAL)
    job_queue.enqueue("low", priority=Priority.LOW)
    job_queue.enqueue("high", priority=Priority.HIGH)

    # Drain runs in manual mode
    ran = job_queue.drain()
    assert ran == 3
    # High (0) must run first, then normal (5), then low (9)
    assert executed == ["high", "normal", "low"]


def test_job_deduplication():
    job_queue.clear()
    records = []

    def sync_task(key):
        records.append(key)

    job_queue.register("sync", sync_task)

    # First enqueue succeeds
    ok1 = job_queue.enqueue("sync", "feed-1", dedupe_key="feed-1")
    assert ok1 is True

    # Second identical enqueue while still waiting is deduplicated
    ok2 = job_queue.enqueue("sync", "feed-1", dedupe_key="feed-1")
    assert ok2 is False

    assert job_queue.pending_count() == 1
    ran = job_queue.drain()
    assert ran == 1
    assert records == ["feed-1"]
    assert job_queue.pending_count() == 0


def test_job_failure_isolation():
    job_queue.clear()
    results = []

    def failing_job():
        raise RuntimeError("Something exploded")

    def succeeding_job():
        results.append("ok")

    job_queue.register("failing", failing_job)
    job_queue.register("succeeding", succeeding_job)

    job_queue.enqueue("failing")
    job_queue.enqueue("succeeding")

    # Draining does not raise an unhandled exception and completes the second job
    ran = job_queue.drain()
    assert ran == 2
    assert results == ["ok"]
