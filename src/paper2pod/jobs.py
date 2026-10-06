"""Background jobs with per-job working directories, progress polling and cancellation.

Each job owns ``<data_dir>/jobs/<job_id>/`` (job.json, paper, script.json, podcast.wav, metrics.json),
so concurrent users never overwrite each other's output. Jobs run on a thread pool, so a web
request or UI callback only submits work and polls; it never blocks for minutes.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .errors import JobCancelled, Paper2PodError
from .models import PodcastRequest

log = logging.getLogger(__name__)
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    request: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    stage: str = "queued"
    progress: int = 0
    message: str = ""
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        data = dict(data)
        data["status"] = JobStatus(data["status"])
        return cls(**data)


class JobStore:
    """Thread-safe job registry persisted as one ``job.json`` per job directory."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}

    def workdir(self, job_id: str) -> Path:
        if not _JOB_ID.match(job_id or ""):
            raise KeyError(f"invalid job id {job_id!r}")
        return self.root / job_id

    def create(self, request: PodcastRequest) -> Job:
        job = Job(id=uuid.uuid4().hex, request=request.to_dict())
        with self._lock:
            self.workdir(job.id).mkdir(parents=True, exist_ok=False)
            self._jobs[job.id] = job
            self._save(job)
        return job

    def get(self, job_id: str) -> Job:
        path = self.workdir(job_id) / "job.json"
        with self._lock:
            if job_id in self._jobs:
                return Job.from_dict(self._jobs[job_id].to_dict())  # a copy, never the live object
            if path.is_file():
                job = Job.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self._jobs[job_id] = job
                return Job.from_dict(job.to_dict())
        raise KeyError(f"unknown job {job_id}")

    def update(self, job_id: str, **changes: Any) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                self.get(job_id)  # loads it from disk or raises KeyError
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = _now()
            self._save(job)
            return Job.from_dict(job.to_dict())

    def list(self) -> list[Job]:
        with self._lock:
            return sorted((Job.from_dict(j.to_dict()) for j in self._jobs.values()),
                          key=lambda j: j.created_at, reverse=True)

    def _save(self, job: Job) -> None:
        path = self.workdir(job.id) / "job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)


PipelineRunner = Callable[..., Any]  # Pipeline.run-compatible callable


class JobRunner:
    """Runs pipeline jobs on a small thread pool."""

    def __init__(self, store: JobStore, run_pipeline: PipelineRunner, max_workers: int = 2):
        self.store = store
        self._run_pipeline = run_pipeline
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="paper2pod-job")
        self._cancel: dict[str, threading.Event] = {}
        self._futures: dict[str, Future] = {}

    def submit(self, request: PodcastRequest) -> Job:
        request.validate()
        job = self.store.create(request)
        self._cancel[job.id] = threading.Event()
        self._futures[job.id] = self._pool.submit(self._execute, job.id, request)
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.store.get(job_id)
        if not job.status.finished and job_id in self._cancel:
            self._cancel[job_id].set()
            if job.status == JobStatus.QUEUED and self._futures[job_id].cancel():
                return self.store.update(job_id, status=JobStatus.CANCELLED, message="Cancelled before start")
        return self.store.get(job_id)

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        future = self._futures.get(job_id)
        if future is not None and not future.cancelled():
            future.result(timeout=timeout)
        return self.store.get(job_id)

    def shutdown(self, wait: bool = True) -> None:
        for event in self._cancel.values():
            event.set()
        self._pool.shutdown(wait=wait, cancel_futures=True)

    def _execute(self, job_id: str, request: PodcastRequest) -> None:
        cancel_event = self._cancel[job_id]

        def check_cancel() -> None:
            if cancel_event.is_set():
                raise JobCancelled("cancelled by user")

        def progress(stage: str, percent: int, message: str) -> None:
            self.store.update(job_id, stage=stage, progress=percent, message=message)

        try:
            check_cancel()
            self.store.update(job_id, status=JobStatus.RUNNING, stage="starting", message="Starting")
            result = self._run_pipeline(request, self.store.workdir(job_id), progress=progress,
                                        check_cancel=check_cancel)
            outputs = getattr(result, "outputs", result) or {}
            self.store.update(job_id, status=JobStatus.SUCCEEDED, progress=100, stage="done",
                              outputs=dict(outputs))
        except JobCancelled:
            self.store.update(job_id, status=JobStatus.CANCELLED, message="Cancelled")
        except Paper2PodError as exc:
            log.warning("job %s failed: %s", job_id, type(exc).__name__)
            self.store.update(job_id, status=JobStatus.FAILED, error=str(exc), message="Failed")
        except Exception as exc:  # noqa: BLE001 - a job must always end in a terminal state
            log.exception("job %s crashed", job_id)
            self.store.update(job_id, status=JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}",
                              message="Failed")
