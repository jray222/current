"""Background work priority queue with single worker thread and manual test mode.

Supports priority levels:
- Priority.HIGH (0): User actions (e.g. on-demand full-text fetch, user manual crawl)
- Priority.NORMAL (5): Scheduled automatic background crawls
- Priority.LOW (9): Maintenance, image downloads, retention pruning

State lives in this process; run the API as a single worker process.
JOB_QUEUE=manual (tests) keeps jobs in memory; `drain()` runs them in the calling thread.
"""
from dataclasses import dataclass, field
import itertools
import os
import queue
import threading
import traceback
from typing import Callable, Any, Optional


class Priority:
    HIGH = 0
    NORMAL = 5
    LOW = 9


@dataclass(order=True)
class PrioritizedJob:
    priority: int
    seq: int
    kind: str = field(compare=False)
    args: tuple = field(compare=False)
    job_key: tuple = field(compare=False)


_handlers: dict[str, Callable] = {}
_pq: "queue.PriorityQueue[PrioritizedJob]" = queue.PriorityQueue()
_pending: set[tuple] = set()
_lock = threading.Lock()
_thread: threading.Thread | None = None
_manual_jobs: list[PrioritizedJob] = []
_seq_counter = itertools.count()


def _is_manual() -> bool:
    return os.environ.get("JOB_QUEUE", "").lower() == "manual"


def register(kind: str, handler: Callable) -> None:
    _handlers[kind] = handler


def _run(kind: str, args: tuple) -> None:
    handler = _handlers.get(kind)
    if handler is None:
        return
    try:
        handler(*args)
    except Exception:
        traceback.print_exc()


def _worker() -> None:
    while True:
        job = _pq.get()
        try:
            _run(job.kind, job.args)
        finally:
            with _lock:
                _pending.discard(job.job_key)
            _pq.task_done()


def enqueue(
    kind: str,
    *args,
    priority: int = Priority.NORMAL,
    dedupe_key: Optional[str] = None,
) -> bool:
    """Queues a job with priority (lower number = higher priority).
    Returns False if an identical job is already queued.
    """
    global _thread
    job_key = (kind, dedupe_key if dedupe_key is not None else tuple(args))

    with _lock:
        if job_key in _pending:
            return False
        _pending.add(job_key)
        seq = next(_seq_counter)
        job = PrioritizedJob(priority=priority, seq=seq, kind=kind, args=tuple(args), job_key=job_key)

    if _is_manual():
        with _lock:
            _manual_jobs.append(job)
            _manual_jobs.sort()
        return True

    _pq.put(job)
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_worker, name="current-jobs", daemon=True)
            _thread.start()
    return True


def drain() -> int:
    """Manual mode: run everything queued so far in priority order. Returns count ran."""
    ran = 0
    while True:
        with _lock:
            if not _manual_jobs:
                break
            job = _manual_jobs.pop(0)

        _run(job.kind, job.args)

        with _lock:
            _pending.discard(job.job_key)
        ran += 1
    return ran


def clear() -> None:
    with _lock:
        _manual_jobs.clear()
        _pending.clear()
        while not _pq.empty():
            try:
                _pq.get_nowait()
                _pq.task_done()
            except queue.Empty:
                break


def pending_count() -> int:
    with _lock:
        return len(_pending)
