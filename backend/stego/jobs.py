"""
Minimal background-job registry so /api/decode can run either synchronously
(blocks the HTTP request, returns the result immediately) or asynchronously
(returns a job_id right away, work happens on a thread pool, the frontend
polls /api/jobs/<id> until it's done). This is the "synchronous and
asynchronous" decoding requirement.

Deliberately not Celery/Redis - this is a single-process demo app, so a
ThreadPoolExecutor plus a dict guarded by a lock is enough, and keeps the
submission dependency-light.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stego-job")
_lock = threading.Lock()
_jobs: dict[str, "Job"] = {}

_JOB_TTL_SECONDS = 30 * 60


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending -> done | error
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)


def _run(job_id: str, fn: Callable, args: tuple, kwargs: dict) -> None:
    try:
        result = fn(*args, **kwargs)
        with _lock:
            job = _jobs.get(job_id)
            if job:
                job.status = "done"
                job.result = result
    except Exception as exc:  # never let a background job crash the process
        with _lock:
            job = _jobs.get(job_id)
            if job:
                job.status = "error"
                job.error = str(exc)


def _sweep_expired() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    for jid in [jid for jid, j in _jobs.items() if j.created_at < cutoff]:
        _jobs.pop(jid, None)


def submit(fn: Callable, *args, **kwargs) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _sweep_expired()
        _jobs[job_id] = Job(id=job_id)
    _executor.submit(_run, job_id, fn, args, kwargs)
    return job_id


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def pop(job_id: str) -> Job | None:
    """Get and remove - used once the frontend has consumed a finished job."""
    with _lock:
        return _jobs.pop(job_id, None)
