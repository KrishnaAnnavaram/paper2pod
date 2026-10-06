"""FastAPI job service (skipped when the [api] extra is not installed)."""
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from paper2pod.api import create_app  # noqa: E402
from paper2pod.runtime import build_runner  # noqa: E402
from paper2pod.sources.local import LocalPaperSource  # noqa: E402


@pytest.fixture
def client(settings):
    runner = build_runner(settings, offline=True)
    yield TestClient(create_app(runner, LocalPaperSource(), settings))
    runner.shutdown()


def test_job_lifecycle(client):
    response = client.post("/jobs", json={"paper": "demo", "minutes": 2})
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(300):
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded", job
    audio = client.get(f"/jobs/{job_id}/audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    script = client.get(f"/jobs/{job_id}/script").json()
    assert script["turns"]


def test_validation_and_errors(client):
    assert client.post("/jobs", json={"paper": "demo", "minutes": 500}).status_code == 422
    assert client.post("/jobs", json={"paper": "demo", "speakers": [{"name": "A"}, {"name": "a"}]}).status_code == 422
    assert client.get("/jobs/" + "0" * 32).status_code == 404
    assert client.get("/jobs/../../etc").status_code == 404


def test_search(client):
    results = client.get("/papers/search", params={"q": "gardens"}).json()
    assert results[0]["title"].startswith("Tiny Recurrent Gardens")
