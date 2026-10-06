"""Streamlit front-end: search, pick a paper, choose length and voices, follow the job.

Run with ``paper2pod ui`` (or ``streamlit run src/paper2pod/ui/streamlit_app.py``).
Work happens on the shared background ``JobRunner``; this script only submits jobs and polls
their status, so the page never blocks and no asyncio loop is started inside a callback.
Each browser session keeps its own job list and chat history in ``st.session_state``.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from paper2pod.chat import ChatSession
from paper2pod.config import Settings, load_dotenv_if_present
from paper2pod.errors import ConfigError
from paper2pod.jobs import JobStatus
from paper2pod.models import PodcastRequest, Speaker
from paper2pod.runtime import build_runner, configure_logging
from paper2pod.services.factory import build_source

st.set_page_config(page_title="paper2pod", page_icon=":studio_microphone:", layout="wide")


@st.cache_resource
def services(offline: bool):
    load_dotenv_if_present()
    settings = Settings.from_env()
    configure_logging(settings)
    return build_runner(settings, offline=offline), build_source(settings, offline=offline)


st.sidebar.title("paper2pod")
offline = st.sidebar.toggle("Offline demo (sample paper, fake voices)", value=False)
try:
    runner, source = services(offline)
except ConfigError as exc:
    st.error(str(exc))
    st.stop()

minutes = st.sidebar.slider("Length (minutes)", 2, 30, 10)
speaker_spec = st.sidebar.text_area(
    "Speakers (one per line: name:role:style[:voice])",
    "Alex:host:female\nSam:expert:male",
    help="role: host | expert | guest; style: male | female | neutral | any",
)
try:
    speakers = [Speaker.parse(line) for line in speaker_spec.splitlines() if line.strip()]
except ValueError as exc:
    st.sidebar.error(str(exc))
    speakers = []

state = st.session_state
state.setdefault("job_ids", [])
state.setdefault("results", [])
if "chat" not in state or state.get("chat_offline") != offline:
    state.chat = ChatSession(runner=runner, source=source, default_minutes=minutes)
    state.chat_offline = offline
state.chat.speakers = speakers or state.chat.speakers
state.chat.default_minutes = minutes


def submit(paper_ref: str) -> None:
    try:
        job = runner.submit(PodcastRequest(paper=paper_ref, minutes=minutes, speakers=speakers))
    except ValueError as exc:
        st.error(str(exc))
        return
    state.job_ids.append(job.id)
    st.toast(f"Started job {job.id[:8]}")


search_tab, chat_tab, jobs_tab = st.tabs(["Search", "Chat", "Jobs"])

with search_tab:
    with st.form("search"):
        query = st.text_input("Search arXiv or paste an arXiv ID / URL", "attention is all you need")
        if st.form_submit_button("Search") and query.strip():
            try:
                state.results = source.search(query, max_results=8)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Search failed: {exc}")
    for paper in state.results:
        with st.container(border=True):
            st.markdown(f"**{paper.title}** · `{paper.arxiv_id}` · {paper.published}")
            st.caption(", ".join(paper.authors[:6]))
            st.write(paper.abstract[:600] + ("…" if len(paper.abstract) > 600 else ""))
            st.button("Make podcast", key=f"make-{paper.arxiv_id}", on_click=submit, args=(paper.arxiv_id,))

with chat_tab:
    for message in state.chat.memory.messages():
        st.chat_message(message["role"]).write(message["content"])
    if prompt := st.chat_input("e.g. find papers on diffusion models"):
        state.chat.send(prompt)
        for job_id in state.chat.job_ids:
            if job_id not in state.job_ids:
                state.job_ids.append(job_id)
        st.rerun()


@st.fragment(run_every="2s")
def job_panel() -> None:
    if not state.job_ids:
        st.info("No jobs yet. Pick a paper in the Search tab.")
        return
    for job_id in reversed(state.job_ids):
        job = runner.store.get(job_id)
        with st.container(border=True):
            st.markdown(f"**{job.request['paper']}** · {job.request['minutes']} min · `{job.id[:8]}` · "
                        f"{job.status.value}")
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                st.progress(job.progress / 100, text=f"{job.stage}: {job.message}")
                st.button("Cancel", key=f"cancel-{job.id}", on_click=runner.cancel, args=(job.id,))
            elif job.status == JobStatus.SUCCEEDED:
                st.audio(Path(job.outputs["audio"]).read_bytes(), format="audio/wav")
                st.caption(f"Files in {Path(job.outputs['audio']).parent}")
            elif job.status == JobStatus.FAILED:
                st.error(job.error)


with jobs_tab:
    job_panel()
