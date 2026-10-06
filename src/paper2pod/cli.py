"""Command-line entry point: ``paper2pod {search,make,demo,serve,ui}``."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .config import Settings, load_dotenv_if_present
from .errors import ConfigError, Paper2PodError
from .jobs import JobStatus, JobStore
from .models import PodcastRequest, Speaker, default_speakers
from .runtime import build_pipeline, configure_logging
from .services.factory import build_source


def _settings(args) -> Settings:
    load_dotenv_if_present()
    settings = Settings.from_env()
    if getattr(args, "backend", None):
        settings = settings.with_overrides(backend=args.backend)
    if getattr(args, "data_dir", None):
        settings = settings.with_overrides(data_dir=Path(args.data_dir))
    return settings


def _run_job(settings: Settings, request: PodcastRequest, offline: bool) -> int:
    pipeline = build_pipeline(settings, offline=offline)
    store = JobStore(settings.jobs_dir)
    job = store.create(request)

    def progress(stage: str, percent: int, message: str) -> None:
        store.update(job.id, stage=stage, progress=percent, message=message)
        print(f"[{percent:3d}%] {stage:<8} {message}", flush=True)

    print(f"job {job.id} -> {store.workdir(job.id)}")
    try:
        result = pipeline.run(request, store.workdir(job.id), progress=progress)
    except KeyboardInterrupt:
        store.update(job.id, status=JobStatus.CANCELLED)
        print("cancelled", file=sys.stderr)
        return 130
    except Paper2PodError as exc:
        store.update(job.id, status=JobStatus.FAILED, error=str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 1
    store.update(job.id, status=JobStatus.SUCCEEDED, progress=100, outputs=result.outputs)
    length = result.metrics["length"]
    print(json.dumps({
        "audio": result.outputs["audio"],
        "script_words": length["script_words"],
        "target_words": length["target_words"],
        "audio_minutes": length["audio_minutes"],
        "grounding_score": result.metrics["grounding"]["score"],
        "format_issues": len(result.metrics["format_issues"]),
    }, indent=2))
    return 0


def cmd_search(args) -> int:
    settings = _settings(args)
    for paper in build_source(settings).search(args.query, max_results=args.n):
        print(f"{paper.arxiv_id:<14} {paper.published}  {paper.title}")
    return 0


def cmd_make(args) -> int:
    settings = _settings(args)
    speakers = [Speaker.parse(s) for s in args.speaker] if args.speaker else default_speakers()
    request = PodcastRequest(paper=args.paper, minutes=args.minutes, speakers=speakers,
                             export_mp3=args.mp3).validate()
    return _run_job(settings, request, offline=False)


def cmd_demo(args) -> int:
    settings = _settings(args).with_overrides(backend="fake")
    request = PodcastRequest(paper="demo", minutes=args.minutes).validate()
    return _run_job(settings, request, offline=True)


def cmd_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print('uvicorn is not installed: pip install "paper2pod[api]"', file=sys.stderr)
        return 1
    uvicorn.run("paper2pod.api:app_from_env", factory=True, host=args.host, port=args.port)
    return 0


def cmd_ui(args) -> int:
    app = Path(__file__).with_name("ui") / "streamlit_app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper2pod", description="Turn arXiv papers into podcasts.")
    parser.add_argument("--data-dir", help="where jobs and caches are stored (default: ./data)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search arXiv")
    p.add_argument("query")
    p.add_argument("-n", type=int, default=5)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("make", help="make a podcast from an arXiv ID or URL")
    p.add_argument("paper")
    p.add_argument("--minutes", type=int, default=10)
    p.add_argument("--speaker", action="append",
                   help='"Name[:role[:style[:voice]]]", repeatable, e.g. --speaker Alex:host:female')
    p.add_argument("--backend", choices=["openai", "fake"], help="override PAPER2POD_BACKEND")
    p.add_argument("--mp3", action="store_true", help="also export MP3 (needs pydub + FFmpeg)")
    p.set_defaults(func=cmd_make)

    p = sub.add_parser("demo", help="fully offline run on a bundled synthetic paper")
    p.add_argument("--minutes", type=int, default=3)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("serve", help="start the FastAPI job service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("ui", help="start the Streamlit UI")
    p.set_defaults(func=cmd_ui)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        configure_logging(_settings(args))
        return args.func(args)
    except (ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
