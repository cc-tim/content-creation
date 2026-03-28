from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.utils.srt import SrtEntry, write_srt

logger = structlog.get_logger()


def extract_narration_segments(script: str) -> list[str]:
    """Extract plain narration text from a script with markers."""
    segments: list[str] = []
    marker_pattern = re.compile(
        r"^\[(HOOK|CONTEXT|RISING|CLIMAX|AFTERMATH|ANALYSIS|"
        r"CLIP:[^\]]+|OVERLAY:[^\]]+|PAUSE:\d+s)\]$"
    )

    for line in script.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if marker_pattern.match(stripped):
            continue
        segments.append(stripped)

    return segments


async def generate_edge_tts(text: str, voice: str, output_path: Path) -> dict[str, Any]:
    """Generate TTS audio using edge-tts. Returns timing metadata."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()

    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    return {
        "duration_ms": 0,  # edge-tts doesn't provide total duration directly
        "word_timings": [],  # simplified for MVP
    }


class TtsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tts"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.script_path or not ctx.script_path.exists():
            raise ValueError("No script available — run scriptwrite stage first")

        logger.info("tts.start", locale=ctx.locale)

        config = PipelineConfig()
        voice = config.get_tts_voice(ctx.locale)
        script_text = ctx.script_path.read_text(encoding="utf-8")

        audio_dir = ctx.work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        segments = extract_narration_segments(script_text)
        logger.info("tts.segments", count=len(segments))

        # Generate audio per segment
        segment_paths: list[Path] = []
        segment_timings: list[dict[str, Any]] = []
        cumulative_ms = 0

        for i, text in enumerate(segments):
            seg_path = audio_dir / f"segment_{i:03d}.mp3"
            timing = await generate_edge_tts(text, voice, seg_path)

            # Estimate duration from file size (~16kB/sec for edge-tts mp3)
            file_size = seg_path.stat().st_size
            est_duration_ms = max(int(file_size / 16 * 1000), 1000)

            segment_timings.append({
                "index": i,
                "text": text,
                "path": str(seg_path),
                "start_ms": cumulative_ms,
                "duration_ms": est_duration_ms,
            })
            segment_paths.append(seg_path)
            cumulative_ms += est_duration_ms

        # Concatenate all segments into one file
        narration_path = audio_dir / f"narration_{ctx.locale}.mp3"
        _concatenate_audio(segment_paths, narration_path)
        ctx.narration_path = narration_path

        # Generate SRT from segment timings
        srt_entries = [
            SrtEntry(
                index=t["index"] + 1,
                start_ms=t["start_ms"],
                end_ms=t["start_ms"] + t["duration_ms"],
                text=t["text"],
            )
            for t in segment_timings
        ]
        subtitle_path = audio_dir / f"subtitles_{ctx.locale}.srt"
        write_srt(srt_entries, subtitle_path)
        ctx.subtitle_path = subtitle_path

        ctx.segment_timings = segment_timings

        logger.info("tts.complete", segments=len(segments), path=str(narration_path))
        return ctx


def _concatenate_audio(paths: list[Path], output: Path) -> None:
    """Concatenate MP3 files by simple binary append (sufficient for MP3)."""
    with open(output, "wb") as out:
        for p in paths:
            out.write(p.read_bytes())
