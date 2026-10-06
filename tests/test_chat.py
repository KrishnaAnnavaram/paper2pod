"""Problems 7 and 8: global/broken memory and history injected twice into the prompt."""
from paper2pod.chat import ChatSession, ConversationMemory, parse_intent
from paper2pod.jobs import JobRunner, JobStatus, JobStore
from paper2pod.sources.local import LocalPaperSource


def fake_pipeline(req, workdir, progress, check_cancel):
    return {"audio": str(workdir / "podcast.wav")}


def session(tmp_path):
    runner = JobRunner(JobStore(tmp_path), fake_pipeline)
    return ChatSession(runner=runner, source=LocalPaperSource()), runner


def test_parse_intent():
    i = parse_intent("Make a 15 minute podcast of arXiv:1706.03762")
    assert (i.kind, i.paper_ref, i.minutes) == ("make", "1706.03762", 15)
    i = parse_intent("find papers about graph neural networks")
    assert (i.kind, i.query) == ("search", "graph neural networks")
    assert parse_intent("podcast the second one, 5 minutes").choice == 2
    assert parse_intent("what's the status?").kind == "status"
    assert parse_intent("1706.03762").kind == "search"
    assert parse_intent("").kind == "help"


def test_memory_is_bounded_by_messages_and_characters():
    memory = ConversationMemory(max_messages=4, max_chars=50)
    for i in range(10):
        memory.add("user", f"message {i}")
    assert len(memory) == 4 and memory.messages()[-1]["content"] == "message 9"
    memory.add("assistant", "x" * 45)
    assert sum(len(m["content"]) for m in memory.messages()) <= 50 or len(memory) == 1


def test_sessions_do_not_share_history_or_jobs(tmp_path):
    a, runner = session(tmp_path)
    b = ChatSession(runner=runner, source=LocalPaperSource())
    a.send("podcast 1706.03762 for 5 minutes")
    assert len(a.memory) == 2 and len(b.memory) == 0
    assert len(a.job_ids) == 1 and b.job_ids == []
    assert "no podcast jobs" in b.send("status")
    runner.shutdown()


def test_history_is_stored_once_and_structured(tmp_path):
    s, runner = session(tmp_path)
    s.send("hello")
    s.send("find papers on recurrent gardens")
    messages = s.memory.messages()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"] == "find papers on recurrent gardens"  # not prefixed with old turns
    runner.shutdown()


def test_search_then_pick_starts_a_job(tmp_path):
    s, runner = session(tmp_path)
    assert "1. Tiny Recurrent Gardens" in s.send("find papers on recurrent gardens")
    reply = s.send("make a 4 minute podcast of the first one")
    assert "Started a 4-minute podcast for demo" in reply
    job = runner.wait(s.job_ids[-1], 5)
    assert job.status == JobStatus.SUCCEEDED
    assert "ready" in s.send("status")
    runner.shutdown()


def test_pick_without_results_asks_for_a_search(tmp_path):
    s, runner = session(tmp_path)
    assert "Search for a paper first" in s.send("make a podcast of the first one")
    runner.shutdown()
