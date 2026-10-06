"""The end-to-end pipeline: fetch -> parse -> outline -> script -> validate -> tts -> mix.

Every stage is a plain method call on injected adapters (paper source, LLM, TTS). Nothing here is
an agent tool and nothing is global: all artefacts go to the job's own ``workdir``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .audio.mix import export_mp3, mix_clips, wav_duration, write_wav
from .audio.text import chunk_for_tts
from .audio.voices import assign_voices
from .config import Settings
from .models import PodcastRequest, Section
from .parsing.sections import paper_sections
from .quality import check_format, check_grounding, check_length, readability
from .script.generate import ScriptWriter
from .script.outline import build_outline
from .services.llm import LLM, MeteredLLM, UsageMeter
from .services.tts import TTSEngine
from .sources.base import PaperSource

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, str], None]
STAGES: dict[str, tuple[int, int]] = {
    "fetch": (0, 8), "parse": (8, 12), "outline": (12, 30), "script": (30, 60),
    "validate": (60, 63), "tts": (63, 96), "mix": (96, 100),
}


def _noop_progress(stage: str, percent: int, message: str) -> None:
    return None


def _noop_cancel() -> None:
    return None


def _write_json(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


@dataclass
class PipelineResult:
    outputs: dict[str, str]
    metrics: dict[str, Any] = field(default_factory=dict)


class Pipeline:
    def __init__(self, settings: Settings, source: PaperSource, llm: LLM, tts: TTSEngine):
        self.settings, self.source, self.llm, self.tts = settings, source, llm, tts

    def _tts_cached(self, text: str, voice: str) -> bytes:
        """Synthesize one chunk, reusing earlier audio for identical (engine, voice, text)."""
        key = hashlib.sha256(f"{self.tts.name}|{self.tts.sample_rate}|{voice}|{text}".encode()).hexdigest()
        path = self.settings.cache_dir / "tts" / f"{key}.pcm"
        if path.is_file():
            return path.read_bytes()
        pcm = self.tts.synthesize(text, voice)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(pcm)
        tmp.replace(path)
        return pcm

    def run(self, request: PodcastRequest, workdir: Path, progress: ProgressFn | None = None,
            check_cancel: Callable[[], None] | None = None) -> PipelineResult:
        request.validate()
        progress = progress or _noop_progress
        check_cancel = check_cancel or _noop_cancel
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        s = self.settings
        meter = UsageMeter()
        llm = MeteredLLM(self.llm, meter)
        timings: dict[str, float] = {}
        outputs: dict[str, str] = {}

        def stage(name: str, fraction: float, message: str) -> None:
            check_cancel()
            lo, hi = STAGES[name]
            progress(name, int(lo + (hi - lo) * max(0.0, min(1.0, fraction))), message)

        # 1. fetch ---------------------------------------------------------------------------------
        t0 = time.perf_counter()
        stage("fetch", 0, "Looking up the paper")
        paper = self.source.resolve(request.paper)
        raw_text = self.source.fetch_fulltext(paper, workdir)
        _write_json(workdir / "paper.json", paper.to_dict())
        timings["fetch"] = time.perf_counter() - t0

        # 2. parse ---------------------------------------------------------------------------------
        t0 = time.perf_counter()
        stage("parse", 0, "Extracting sections")
        sections = paper_sections(raw_text)
        _write_json(workdir / "sections.json", [{"title": x.title, "words": x.words} for x in sections])
        if not paper.abstract:
            paper.abstract = next((x.text for x in sections if x.title.lower() == "abstract"), "")
        timings["parse"] = time.perf_counter() - t0
        log.info("parsed %d sections", len(sections))

        # 3. outline -------------------------------------------------------------------------------
        t0 = time.perf_counter()
        stage("outline", 0, "Summarising each section")
        outline = build_outline(
            paper, sections, llm,
            on_item=lambda i, n: stage("outline", i / n, f"Summarised part {i} of {n}"),
            check_cancel=check_cancel,
        )
        _write_json(workdir / "outline.json", [o.to_dict() for o in outline])
        timings["outline"] = time.perf_counter() - t0

        # 4. script --------------------------------------------------------------------------------
        t0 = time.perf_counter()
        stage("script", 0, f"Writing a {request.minutes}-minute script")
        writer = ScriptWriter(llm, words_per_minute=s.words_per_minute, tolerance=s.length_tolerance,
                              max_segment_words=s.max_segment_words, max_regenerations=s.max_regenerations)
        script, segment_reports = writer.write(
            paper, outline, request.speakers, request.minutes,
            on_segment=lambda i, n: stage("script", i / n, f"Wrote segment {i} of {n}"),
            check_cancel=check_cancel,
        )
        outputs["script"] = str(_write_json(workdir / "script.json", script.to_dict()))
        timings["script"] = time.perf_counter() - t0

        # 5. validate ------------------------------------------------------------------------------
        stage("validate", 0, "Checking format and grounding")
        source_text = "\n\n".join([paper.title, paper.abstract] + [x.text for x in sections or [Section("", raw_text)]])
        format_issues = check_format(script)
        grounding = check_grounding(script, source_text)
        style = readability(script)

        # 6. tts -----------------------------------------------------------------------------------
        t0 = time.perf_counter()
        voices = assign_voices(request.speakers, overrides=s.voice_overrides)
        clips: list[tuple[int, bytes]] = []
        total = len(script.turns)
        for n, turn in enumerate(script.turns, start=1):
            stage("tts", (n - 1) / total, f"Voicing turn {n} of {total}")
            pcm = b"".join(self._tts_cached(chunk, voices[turn.speaker])
                           for chunk in chunk_for_tts(turn.text, self.tts.max_chars))
            clips.append((turn.segment, pcm))
        timings["tts"] = time.perf_counter() - t0

        # 7. mix -----------------------------------------------------------------------------------
        t0 = time.perf_counter()
        stage("mix", 0, "Mixing audio")
        pcm, chapters = mix_clips(clips, script.segment_titles, self.tts.sample_rate, s.pause_ms)
        wav_path = write_wav(workdir / "podcast.wav", pcm, self.tts.sample_rate)
        outputs["audio"] = str(wav_path)
        audio_seconds = wav_duration(wav_path)
        outputs["chapters"] = str(_write_json(workdir / "chapters.json", [c.to_dict() for c in chapters]))
        if request.export_mp3:
            outputs["mp3"] = str(export_mp3(wav_path, workdir / "podcast.mp3"))
        timings["mix"] = time.perf_counter() - t0

        length = check_length(script, request.minutes, s.words_per_minute, s.length_tolerance, audio_seconds)
        metrics = {
            "paper": {"arxiv_id": paper.arxiv_id, "title": paper.title, "sections": len(sections)},
            "models": {"llm": self.llm.name, "tts": self.tts.name},
            "voices": voices,
            "length": length.to_dict(),
            "segments": [r.to_dict() for r in segment_reports],
            "format_issues": format_issues,
            "grounding": grounding.to_dict(),
            "readability": style.to_dict(),
            "usage": meter.to_dict(),
            "timings_seconds": {k: round(v, 3) for k, v in timings.items()},
        }
        outputs["metrics"] = str(_write_json(workdir / "metrics.json", metrics))
        progress("done", 100, f"Done: {length.audio_minutes} minutes of audio")
        return PipelineResult(outputs=outputs, metrics=metrics)
