from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.utils.srt import SrtEntry, write_srt
from pipeline.voices.registry import VoiceRegistry

logger = structlog.get_logger()


def extract_narration_segments(script: str) -> list[str]:
    """Extract plain narration text from a script with markers."""
    segments: list[str] = []
    # Match all marker formats including extended ones like [HOOK - 0:00-0:30]
    marker_pattern = re.compile(
        r"^\["
        r"(HOOK|CONTEXT|RISING|CLIMAX|AFTERMATH|ANALYSIS|RISING ACTION)"
        r"(\s*-\s*[^\]]+)?"  # optional timestamp suffix like " - 0:00-0:30"
        r"\]$"
        r"|"
        r"^\[CLIP:[^\]]+\]$"
        r"|"
        r"^\[OVERLAY:[^\]]+\]$"
        r"|"
        r"^\[PAUSE:\d+s\]$"
    )

    for line in script.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if marker_pattern.match(stripped):
            continue
        segments.append(stripped)

    return segments


class TtsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tts"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.script_path or not ctx.script_path.exists():
            raise ValueError("No script available — run scriptwrite stage first")

        logger.info("tts.start", locale=ctx.locale)

        config = PipelineConfig()
        registry = VoiceRegistry(config.VOICES_DIR)
        if ctx.voice_id:
            engine, profile = registry.resolve(ctx.voice_id)
        else:
            engine, profile = registry.default_for_locale(ctx.locale)

        script_text = ctx.script_path.read_text(encoding="utf-8")

        audio_dir = ctx.work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        segments = extract_narration_segments(script_text)
        logger.info("tts.segments", count=len(segments))

        # Compose inserts a silent video gap after each scene (see
        # ComposeStage._silence_gap), but the audio file is a plain
        # concatenation of segments with no silence between them. To keep the
        # SRT subtitles aligned with the rendered video, we have to add each
        # scene's pause_after_sec into the cumulative SRT timeline.
        scene_pauses_ms: list[int] = []
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard

            storyboard = Storyboard.load(ctx.storyboard_path)
            scene_pauses_ms = [int(s.pause_after_sec * 1000) for s in storyboard.scenes]

        # Generate audio per segment
        segment_paths: list[Path] = []
        segment_timings: list[dict[str, Any]] = []
        cumulative_ms = 0

        # Scene ids align 1:1 with segments when the storyboard is present
        # (storyboard.derive_script emits one narration line per scene).
        scene_ids: list[str | None] = []
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard

            storyboard_for_ids = Storyboard.load(ctx.storyboard_path)
            scene_ids = [s.id for s in storyboard_for_ids.scenes]

        for i, text in enumerate(segments):
            seg_path = audio_dir / f"segment_{i:03d}.mp3"
            scene_id = scene_ids[i] if i < len(scene_ids) else None
            # Engines are sync and some (EdgeEngine) call asyncio.run internally,
            # which blows up inside this running loop. Offload to a worker thread.
            await asyncio.to_thread(engine.synthesize, text, seg_path, profile, scene_id=scene_id)

            # Get actual duration via ffprobe
            est_duration_ms = _get_audio_duration_ms(seg_path)

            segment_timings.append(
                {
                    "index": i,
                    "text": text,
                    "path": str(seg_path),
                    "start_ms": cumulative_ms,
                    "duration_ms": est_duration_ms,
                }
            )
            segment_paths.append(seg_path)
            cumulative_ms += est_duration_ms
            # Account for the inter-scene pause that compose will insert.
            if i < len(scene_pauses_ms):
                cumulative_ms += scene_pauses_ms[i]

        # Concatenate all segments into one file
        narration_path = audio_dir / f"narration_{ctx.locale}.mp3"
        _concatenate_audio(segment_paths, narration_path)
        ctx.narration_path = narration_path

        # Generate SRT from segment timings — split long text into subtitle chunks
        srt_entries = _build_subtitle_entries(segment_timings)
        subtitle_path = audio_dir / f"subtitles_{ctx.locale}.srt"
        write_srt(srt_entries, subtitle_path)
        ctx.subtitle_path = subtitle_path

        ctx.segment_timings = segment_timings

        logger.info("tts.complete", segments=len(segments), path=str(narration_path))
        return ctx


def _visual_width(text: str) -> int:
    """Estimate visual width: CJK chars count as 2, Latin/digits as 1."""
    width = 0
    for ch in text:
        if "\u2e80" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff" or "\ufe30" <= ch <= "\ufe4f":
            width += 2
        elif "\uff00" <= ch <= "\uffef":
            width += 2  # fullwidth forms
        else:
            width += 1
    return width


def _wrap_english_two_lines(text: str, chars_per_line: int = 42) -> str:
    """Wrap English text to at most 2 lines at a word boundary, line 1 \u2264 chars_per_line."""
    if len(text) <= chars_per_line:
        return text
    words = text.split()
    line1 = ""
    for i, word in enumerate(words):
        candidate = (line1 + " " + word).strip() if line1 else word
        if len(candidate) <= chars_per_line:
            line1 = candidate
        else:
            line2 = " ".join(words[i:])
            return line1 + "\n" + line2
    return line1


def _split_long_sentence(text: str, max_chars: int) -> list[str]:
    """Split a long English sentence into pieces of \u2264 max_chars at word boundaries."""
    words = text.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def _split_english_subtitles(text: str, chars_per_line: int = 42) -> list[str]:
    """Split English narration into subtitle chunks of max 2 lines \u00d7 chars_per_line.

    Splits first on sentence boundaries, accumulates into ~84-char chunks,
    then wraps each chunk to 2 lines.
    """
    import re

    max_chunk = chars_per_line * 2

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    raw_chunks: list[str] = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) > max_chunk:
            if current:
                raw_chunks.append(current)
                current = ""
            raw_chunks.extend(_split_long_sentence(sent, max_chunk))
        else:
            candidate = (current + " " + sent).strip() if current else sent
            if len(candidate) <= max_chunk:
                current = candidate
            else:
                raw_chunks.append(current)
                current = sent

    if current:
        raw_chunks.append(current)

    return [_wrap_english_two_lines(c, chars_per_line) for c in raw_chunks if c.strip()]


def _wrap_subtitle_line(text: str, max_width: int = 36) -> str:
    """Insert newline breaks into a subtitle chunk, respecting word boundaries.

    CJK characters can break anywhere, but Latin/digit words must stay whole.
    Uses visual width (CJK=2, Latin=1) so lines look balanced on screen.
    Returns text with actual newlines for SRT format (max 2 lines).
    """
    import re

    if _visual_width(text) <= max_width:
        return text

    # Tokenize into CJK chars and Latin words
    tokens: list[str] = re.findall(r"[A-Za-z0-9]+|.", text)

    line = ""
    lines: list[str] = []
    for token in tokens:
        if _visual_width(line) + _visual_width(token) > max_width and line:
            lines.append(line)
            line = token
        else:
            line += token
    if line:
        lines.append(line)

    # Max 2 lines per subtitle — use real newlines (SRT format)
    if len(lines) <= 2:
        return "\n".join(lines)
    return "\n".join(["".join(lines[: len(lines) // 2]), "".join(lines[len(lines) // 2 :])])


def _split_text_for_subtitles(text: str, max_width: int = 36) -> list[str]:
    """Split text into subtitle-sized chunks.

    For CJK text, split by punctuation first (。！？，、；),
    then by visual width if still too long. Max 2 lines per subtitle.
    Uses visual width (CJK=2, Latin=1) so lines look balanced on screen.
    Latin/English words are never broken mid-word.
    For predominantly English text, delegates to _split_english_subtitles.
    """
    import re

    # Route predominantly English text (< 20% CJK chars) to the English splitter.
    non_space = text.replace(" ", "")
    if non_space:
        cjk_count = sum(
            1
            for ch in non_space
            if "⺀" <= ch <= "鿿"
            or "豈" <= ch <= "﫿"
            or "︰" <= ch <= "﹏"
            or "＀" <= ch <= "￯"
        )
        if cjk_count / len(non_space) < 0.2:
            return _split_english_subtitles(text)

    # Split on CJK sentence-ending punctuation
    parts = re.split(r"([。！？；])", text)

    # Rejoin punctuation with preceding text
    chunks: list[str] = []
    current = ""
    for part in parts:
        if re.match(r"^[。！？；]$", part):
            current += part
            if _visual_width(current) >= max_width:
                chunks.append(current.strip())
                current = ""
        else:
            if current:
                if _visual_width(current) + _visual_width(part) > max_width * 2:
                    chunks.append(current.strip())
                    current = part
                else:
                    current += part
            else:
                current = part

    if current.strip():
        chunks.append(current.strip())

    # Further split any chunk that's still too long
    result: list[str] = []
    for chunk in chunks:
        if _visual_width(chunk) <= max_width * 2:
            result.append(_wrap_subtitle_line(chunk, max_width))
        else:
            # Split by comma or mid-point
            sub_parts = re.split(r"([，、])", chunk)
            sub_current = ""
            for sp in sub_parts:
                if _visual_width(sub_current) + _visual_width(sp) > max_width * 2:
                    if sub_current.strip():
                        result.append(_wrap_subtitle_line(sub_current.strip(), max_width))
                    sub_current = sp
                else:
                    sub_current += sp
            if sub_current.strip():
                result.append(_wrap_subtitle_line(sub_current.strip(), max_width))

    return [r for r in result if r]


def _build_subtitle_entries(
    segment_timings: list[dict[str, Any]],
) -> list[SrtEntry]:
    """Build SRT entries from segment timings, splitting long text into chunks.

    Each subtitle shows max ~36 CJK characters (2 lines of ~18).
    Timing is distributed proportionally across chunks within each segment.
    """
    entries: list[SrtEntry] = []
    index = 1

    for t in segment_timings:
        text = t["text"]
        start_ms = t["start_ms"]
        duration_ms = t["duration_ms"]

        chunks = _split_text_for_subtitles(text, max_width=36)
        if not chunks:
            continue

        # Distribute time proportionally by character count
        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            continue

        chunk_start = start_ms
        for chunk in chunks:
            proportion = len(chunk) / total_chars
            chunk_duration = int(duration_ms * proportion)
            chunk_end = chunk_start + chunk_duration

            entries.append(
                SrtEntry(
                    index=index,
                    start_ms=chunk_start,
                    end_ms=chunk_end,
                    text=chunk,
                )
            )
            index += 1
            chunk_start = chunk_end

    return entries


def _get_audio_duration_ms(path: Path) -> int:
    """Get audio duration in milliseconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(float(result.stdout.strip()) * 1000)
    except Exception:
        # Fallback: estimate from file size (~16kB/sec for edge-tts mp3)
        file_size = path.stat().st_size
        return max(int(file_size / 16 * 1000), 1000)


def _concatenate_audio(paths: list[Path], output: Path) -> None:
    """Concatenate MP3 files by simple binary append (sufficient for MP3)."""
    with open(output, "wb") as out:
        for p in paths:
            out.write(p.read_bytes())
