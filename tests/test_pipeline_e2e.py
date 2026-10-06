"""End to end, fully offline: sample paper -> fake LLM -> fake TTS -> WAV + metrics."""
import json
from pathlib import Path

from paper2pod import cli
from paper2pod.cli import main
from paper2pod.errors import MissingDependency, TransientError
from paper2pod.jobs import JobRunner, JobStatus, JobStore
from paper2pod.models import PodcastRequest, Script
from paper2pod.runtime import build_pipeline


def test_offline_pipeline_produces_all_artifacts(settings, tmp_path):
    pipeline = build_pipeline(settings, offline=True)
    events = []
    result = pipeline.run(PodcastRequest(paper="demo", minutes=4), tmp_path / "job",
                          progress=lambda stage, pct, msg: events.append((stage, pct)))
    for key in ("audio", "script", "metrics", "chapters"):
        assert Path(result.outputs[key]).is_file()

    metrics = json.loads(Path(result.outputs["metrics"]).read_text())
    length = metrics["length"]
    assert length["target_words"] == 600 and length["within_tolerance"]
    assert 3.8 <= length["audio_minutes"] <= 4.6          # measured from the WAV file
    assert metrics["grounding"]["score"] == 1.0
    assert metrics["format_issues"] == []
    assert metrics["voices"] == {"Alex": "nova", "Sam": "onyx"}
    assert metrics["usage"]["calls"]["write_segment"] >= 3

    script = Script.from_dict(json.loads(Path(result.outputs["script"]).read_text()))
    assert {t.speaker for t in script.turns} == {"Alex", "Sam"}
    assert "reference" not in " ".join(t.text for t in script.turns).lower()

    percents = [p for _, p in events]
    assert percents == sorted(percents) and percents[-1] == 100


def test_tts_audio_is_cached_between_runs(settings, tmp_path):
    pipeline = build_pipeline(settings, offline=True)
    pipeline.run(PodcastRequest(paper="demo", minutes=2), tmp_path / "a")
    calls = len(pipeline.tts.calls)
    pipeline.run(PodcastRequest(paper="demo", minutes=2), tmp_path / "b")
    assert len(pipeline.tts.calls) == calls  # identical turns reused cached audio


def test_pipeline_through_job_runner(settings):
    pipeline = build_pipeline(settings, offline=True)
    runner = JobRunner(JobStore(settings.jobs_dir), pipeline.run)
    job = runner.wait(runner.submit(PodcastRequest(paper="demo", minutes=2)).id, 60)
    assert job.status == JobStatus.SUCCEEDED and job.progress == 100
    assert Path(job.outputs["audio"]).parent.name == job.id
    runner.shutdown()


def test_cli_demo(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "demo", "--minutes", "2"]) == 0
    out = capsys.readouterr().out
    summary = json.loads(out[out.index("{"):])
    assert summary["grounding_score"] == 1.0 and Path(summary["audio"]).is_file()


def test_cli_marks_the_job_running_while_the_pipeline_works(tmp_path, monkeypatch, capsys):
    seen = {}
    real_build = cli.build_pipeline

    def spy_build(settings, offline=False):
        pipeline = real_build(settings, offline=offline)
        real_run = pipeline.run

        def spy_run(request, workdir, progress=None, check_cancel=None):
            seen["status"] = json.loads((Path(workdir) / "job.json").read_text())["status"]
            return real_run(request, workdir, progress=progress, check_cancel=check_cancel)

        pipeline.run = spy_run
        return pipeline

    monkeypatch.setattr(cli, "build_pipeline", spy_build)
    assert main(["--data-dir", str(tmp_path), "demo", "--minutes", "2"]) == 0
    assert seen["status"] == "running"
    job_files = list((tmp_path / "jobs").glob("*/job.json"))
    assert json.loads(job_files[0].read_text())["status"] == "succeeded"


def test_cli_records_a_value_error_as_a_failed_job(tmp_path, monkeypatch, capsys):
    class BrokenPipeline:
        def run(self, request, workdir, progress=None, check_cancel=None):
            raise ValueError("unknown voice 'robot' for Alex")

    monkeypatch.setattr(cli, "build_pipeline", lambda settings, offline=False: BrokenPipeline())
    assert main(["--data-dir", str(tmp_path), "demo", "--minutes", "2"]) == 1
    job = json.loads(next((tmp_path / "jobs").glob("*/job.json")).read_text())
    assert job["status"] == "failed" and "robot" in job["error"]


def test_cli_reports_package_errors_without_a_traceback(tmp_path, monkeypatch, capsys):
    class DownSource:
        def search(self, query, max_results=5):
            raise TransientError("network error: arXiv is down")

    monkeypatch.setattr(cli, "build_source", lambda settings, offline=False: DownSource())
    assert main(["--data-dir", str(tmp_path), "search", "graph transformers"]) == 1
    assert "arXiv is down" in capsys.readouterr().err

    def missing_extra(settings, offline=False):
        raise MissingDependency("openai", "openai")

    monkeypatch.setattr(cli, "build_pipeline", missing_extra)
    assert main(["--data-dir", str(tmp_path), "demo"]) == 1
    assert 'pip install "paper2pod[openai]"' in capsys.readouterr().err
