"""FastAPI job service (``pip install "paper2pod[api]"``, then ``paper2pod serve``).

POST /jobs              start a podcast job (returns immediately with a job id)
GET  /jobs/{id}         status, stage, progress, outputs
POST /jobs/{id}/cancel  request cancellation
GET  /jobs/{id}/audio   the finished WAV (or MP3 when requested)
GET  /jobs/{id}/script  the structured script (JSON)
GET  /papers/search     arXiv search
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from .config import Settings
from .jobs import JobRunner, JobStatus
from .models import PodcastRequest, Speaker
from .sources.base import PaperSource

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import FileResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    from .errors import MissingDependency

    raise MissingDependency("fastapi", "api") from exc


class SpeakerIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    role: Literal["host", "expert", "guest"] = "guest"
    voice_style: Literal["male", "female", "neutral", "any"] = "any"
    voice: str | None = None


class JobIn(BaseModel):
    paper: str = Field(min_length=1, max_length=200, description="arXiv ID or URL")
    minutes: int = Field(10, ge=2, le=60)
    speakers: list[SpeakerIn] = Field(default_factory=lambda: [
        SpeakerIn(name="Alex", role="host", voice_style="female"),
        SpeakerIn(name="Sam", role="expert", voice_style="male"),
    ])
    export_mp3: bool = False


def create_app(runner: JobRunner, source: PaperSource, settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="paper2pod", version="0.1.0")

    def get_job(job_id: str):
        try:
            return runner.store.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found") from None

    @app.get("/health")
    def health():
        return {"status": "ok", "backend": settings.backend if settings else "unknown"}

    @app.post("/jobs", status_code=202)
    def create_job(body: JobIn):
        try:
            request = PodcastRequest(
                paper=body.paper, minutes=body.minutes, export_mp3=body.export_mp3,
                speakers=[Speaker(s.name, s.role, s.voice_style, s.voice) for s in body.speakers],
            )
            job = runner.submit(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return job.to_dict()

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str):
        return get_job(job_id).to_dict()

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        get_job(job_id)
        return runner.cancel(job_id).to_dict()

    @app.get("/jobs/{job_id}/audio")
    def job_audio(job_id: str):
        job = get_job(job_id)
        if job.status != JobStatus.SUCCEEDED:
            raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
        path = Path(job.outputs.get("mp3") or job.outputs["audio"])
        media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
        return FileResponse(path, media_type=media, filename=f"paper2pod-{job_id[:8]}{path.suffix}")

    @app.get("/jobs/{job_id}/script")
    def job_script(job_id: str):
        job = get_job(job_id)
        if "script" not in job.outputs:
            raise HTTPException(status_code=409, detail="script not ready")
        return json.loads(Path(job.outputs["script"]).read_text(encoding="utf-8"))

    @app.get("/papers/search")
    def search(q: str = Query(min_length=2, max_length=300), max_results: int = Query(5, ge=1, le=25)):
        return [p.to_dict() for p in source.search(q, max_results=max_results)]

    return app


def app_from_env() -> FastAPI:  # used by ``paper2pod serve``
    from .config import load_dotenv_if_present
    from .runtime import build_runner, configure_logging
    from .services.factory import build_source

    load_dotenv_if_present()
    settings = Settings.from_env()
    configure_logging(settings)
    return create_app(build_runner(settings), build_source(settings), settings)
