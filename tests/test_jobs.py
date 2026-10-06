"""Problems 6 and 12: shared global output, and blocking work inside the UI callback."""
import threading
import time

import pytest

from paper2pod.errors import JobCancelled, PaperNotFound
from paper2pod.jobs import JobRunner, JobStatus, JobStore
from paper2pod.models import PodcastRequest


def request(paper="demo"):
    return PodcastRequest(paper=paper, minutes=3)


def writing_pipeline(req, workdir, progress, check_cancel):
    progress("script", 50, "half way")
    out = workdir / "podcast.wav"
    out.write_text(req.paper)
    return {"audio": str(out)}


def test_each_job_gets_its_own_directory_and_output(tmp_path):
    runner = JobRunner(JobStore(tmp_path), writing_pipeline, max_workers=2)
    a, b = runner.submit(request("1706.03762")), runner.submit(request("2101.00001"))
    a, b = runner.wait(a.id, 5), runner.wait(b.id, 5)
    assert a.status == b.status == JobStatus.SUCCEEDED
    assert a.outputs["audio"] != b.outputs["audio"]
    assert open(a.outputs["audio"]).read() == "1706.03762"
    assert open(b.outputs["audio"]).read() == "2101.00001"
    runner.shutdown()


def test_submit_returns_immediately_and_progress_is_pollable(tmp_path):
    release = threading.Event()

    def slow(req, workdir, progress, check_cancel):
        progress("tts", 70, "voicing")
        release.wait(5)
        return {}

    runner = JobRunner(JobStore(tmp_path), slow)
    started = time.perf_counter()
    job = runner.submit(request())
    assert time.perf_counter() - started < 1
    for _ in range(100):
        if runner.store.get(job.id).progress == 70:
            break
        time.sleep(0.02)
    assert runner.store.get(job.id).stage == "tts"
    release.set()
    assert runner.wait(job.id, 5).status == JobStatus.SUCCEEDED
    runner.shutdown()


def test_cancel_stops_a_running_job(tmp_path):
    started = threading.Event()

    def cancellable(req, workdir, progress, check_cancel):
        started.set()
        for _ in range(500):
            check_cancel()
            time.sleep(0.01)
        return {}

    runner = JobRunner(JobStore(tmp_path), cancellable)
    job = runner.submit(request())
    started.wait(5)
    runner.cancel(job.id)
    assert runner.wait(job.id, 5).status == JobStatus.CANCELLED
    runner.shutdown()


def test_failures_are_recorded_not_raised(tmp_path):
    def failing(req, workdir, progress, check_cancel):
        raise PaperNotFound("arXiv has no paper with ID 2101.99999")

    runner = JobRunner(JobStore(tmp_path), failing)
    job = runner.wait(runner.submit(request()).id, 5)
    assert job.status == JobStatus.FAILED and "2101.99999" in job.error
    runner.shutdown()


def test_job_state_survives_a_new_store(tmp_path):
    runner = JobRunner(JobStore(tmp_path), writing_pipeline)
    job = runner.wait(runner.submit(request()).id, 5)
    reloaded = JobStore(tmp_path).get(job.id)
    assert reloaded.status == JobStatus.SUCCEEDED and reloaded.outputs == job.outputs
    runner.shutdown()


def test_job_ids_cannot_escape_the_jobs_directory(tmp_path):
    store = JobStore(tmp_path)
    for bad in ["../etc", "..", "abc", "A" * 32]:
        with pytest.raises(KeyError):
            store.get(bad)


def test_invalid_requests_are_rejected_before_queueing(tmp_path):
    runner = JobRunner(JobStore(tmp_path), writing_pipeline)
    with pytest.raises(ValueError):
        runner.submit(PodcastRequest(paper="demo", minutes=500))
    assert runner.store.list() == []
    runner.shutdown()


def test_job_cancelled_is_a_package_error():
    assert issubclass(JobCancelled, Exception)
