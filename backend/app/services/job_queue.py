"""Background work (collecting deck pictures) on one worker thread, like Glance's AI queue but simpler.

Requests only enqueue; a single daemon thread runs one job at a time, each handler opening its own
short database session. State lives in this process, so run the API as one worker (the Docker image
does). Decks still queued or collecting at shutdown are re-queued at startup (collector.resume).

JOB_QUEUE=manual (tests) keeps jobs in a list instead; `drain()` runs them in the calling thread.
"""
import os
import queue
import threading
import traceback
from typing import Callable

_handlers: dict[str, Callable] = {}
_q: "queue.Queue[tuple[str, tuple]]" = queue.Queue()
_pending: set[tuple[str, tuple]] = set()
_lock = threading.Lock()
_thread: threading.Thread | None = None
_manual_jobs: list[tuple[str, tuple]] = []


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
    except Exception:  # a failing job must never stop the worker
        traceback.print_exc()


def _worker() -> None:
    while True:
        kind, args = _q.get()
        try:
            _run(kind, args)
        finally:
            with _lock:
                _pending.discard((kind, args))
            _q.task_done()


def enqueue(kind: str, *args) -> bool:
    """Queues a job; False if the same one is already waiting."""
    global _thread
    job = (kind, tuple(args))
    with _lock:
        if job in _pending:
            return False
        _pending.add(job)
    if _is_manual():
        _manual_jobs.append(job)
        return True
    _q.put(job)
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_worker, name="current-jobs", daemon=True)
            _thread.start()
    return True


def drain() -> int:
    """Manual mode: run everything queued so far (and what that queues) here. Returns how many ran."""
    ran = 0
    while _manual_jobs:
        kind, args = _manual_jobs.pop(0)
        _run(kind, args)
        with _lock:
            _pending.discard((kind, args))
        ran += 1
    return ran


def clear() -> None:
    with _lock:
        _manual_jobs.clear()
        _pending.clear()


def pending_count() -> int:
    with _lock:
        return len(_pending)
