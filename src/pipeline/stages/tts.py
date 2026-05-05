from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipeline.storyboard import Scene, Storyboard
    from pipeline.voices.registry import VoiceRegistry

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.utils.srt import SrtEntry, write_srt
from pipeline.voices.registry import VoiceRegistry

logger = structlog.get_logger()


def extract_narration_segments(script: str) -> list[str]:
    """Extract plain narration text from a script with markers."""
    segments: list[str] = []
    # Match section markers (any [ALL_CAPS] or [ALL_CAPS - suffix] form),
    # plus CLIP/OVERLAY/PAUSE directives. Using a general uppercase pattern
    # so derive_script() section names don't need to be hardcoded here.
    marker_pattern = re.compile(
        r"^\[[A-Z][A-Z0-9_ ]*(\s*-\s*[^\]]+)?\]$"
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


def _transcode_to_mp3(src: Path, dst: Path) -> None:
    """Transcode any ffmpeg-readable audio file to MP3 at dst."""
    import subprocess as _sp
    dst.parent.mkdir(parents=True, exist_ok=True)
    _sp.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(dst),
        ],
        check=True,
    )


def _resolve_per_scene_engine(
    *,
    scene: Scene | None,
    registry: VoiceRegistry | None,
    default_engine: Any,
    default_profile: Any,
) -> tuple[Any, Any] | None:
    """Resolve the (engine, profile) tuple to use for this scene's narration.

    Returns:
      - (engine, profile) — when the scene has a narration_source that resolves
        to a TTS engine (engine=edge or fish_audio) successfully via the registry.
      - None — signals "use direct transcode" (engine=prerecorded with file=...).
        The caller is responsible for invoking _transcode_to_mp3 in that case.

    On any resolution failure (missing scene, no narration_source, voice not in
    registry, registry is None), returns (default_engine, default_profile) so the
    caller falls back to the call-level defaults. A warning is logged when the
    fallback is due to an unresolvable per-scene voice id.
    """
    if scene is None or scene.narration_source is None or registry is None:
        return default_engine, default_profile

    ns = scene.narration_source
    if ns.engine == "prerecorded":
        return None  # signal: caller should direct-transcode the file

    # edge / fish_audio — resolve through registry; fall back on miss.
    try:
        return registry.resolve(ns.voice)  # type: ignore[arg-type]
    except Exception as exc:  # VoiceNotFound or anything else
        logger.warning(
            "tts.per_scene.voice_unresolved",
            scene_id=scene.id,
            voice_id=ns.voice,
            error=str(exc),
        )
        return default_engine, default_profile


async def _synthesize_pass(
    segments: list[str],
    scene_ids: list[str | None],
    scene_pauses_ms: list[int],
    audio_dir: Path,
    locale_tag: str,
    engine: Any,
    profile: Any,
    seg_prefix: str = "segment",
    *,
    registry: VoiceRegistry | None = None,
    storyboard: Storyboard | None = None,
    project_root: Path | None = None,
) -> tuple[Path, Path, list[dict[str, Any]]]:
    """Run TTS synthesis for one pass (primary or secondary).

    Segments that are empty strings are skipped — a 0ms placeholder timing
    is inserted so the index alignment between primary and secondary is
    preserved. Empty segments are excluded from duration-check logic.

    Returns (narration_path, subtitle_path, segment_timings).
    """
    segment_paths: list[Path] = []
    segment_timings: list[dict[str, Any]] = []
    cumulative_ms = 0

    for i, text in enumerate(segments):
        scene_id = scene_ids[i] if i < len(scene_ids) else None
        if not text:
            # Warn about missing EN narration; insert 0ms placeholder to keep indices aligned.
            logger.warning(
                "tts.secondary.missing_narration_en",
                scene_id=scene_id,
                index=i,
            )
            segment_timings.append(
                {
                    "index": i,
                    "text": "",
                    "path": None,
                    "start_ms": cumulative_ms,
                    "duration_ms": 0,
                    "skipped": True,
                }
            )
            if i < len(scene_pauses_ms):
                cumulative_ms += scene_pauses_ms[i]
            continue

        seg_path = audio_dir / f"{seg_prefix}_{i:03d}.mp3"
        # Per-scene narration_source override (Plan 2). Resolve which engine
        # to use for this segment.
        scene_obj = (
            storyboard.get_scene(scene_id) if (storyboard is not None and scene_id) else None
        )
        resolved = _resolve_per_scene_engine(
            scene=scene_obj,
            registry=registry,
            default_engine=engine,
            default_profile=profile,
        )

        if resolved is None:
            # Direct-transcode path (engine="prerecorded" + file=...).
            assert scene_obj is not None and scene_obj.narration_source is not None
            ns = scene_obj.narration_source
            assert ns.file is not None
            src_path = (project_root / ns.file) if project_root else Path(ns.file)
            if not src_path.exists():
                logger.warning(
                    "tts.prerecorded.missing_file_falling_back_to_default",
                    scene_id=scene_id,
                    file=str(src_path),
                )
                # Fall back: use the default engine for this segment.
                await asyncio.to_thread(
                    engine.synthesize, text, seg_path, profile, scene_id=scene_id
                )
            else:
                logger.info("tts.prerecorded.transcode", scene_id=scene_id, src=str(src_path))
                await asyncio.to_thread(_transcode_to_mp3, src_path, seg_path)
        else:
            seg_engine, seg_profile = resolved
            # Engines are sync and some (EdgeEngine) call asyncio.run internally,
            # which blows up inside this running loop. Offload to a worker thread.
            await asyncio.to_thread(
                seg_engine.synthesize, text, seg_path, seg_profile, scene_id=scene_id,
            )

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
        if i < len(scene_pauses_ms):
            cumulative_ms += scene_pauses_ms[i]

    narration_path = audio_dir / f"narration_{locale_tag}.mp3"
    _concatenate_audio(segment_paths, narration_path)

    srt_entries = _build_subtitle_entries(
        [t for t in segment_timings if not t.get("skipped")]
    )
    subtitle_path = audio_dir / f"subtitles_{locale_tag}.srt"
    write_srt(srt_entries, subtitle_path)

    return narration_path, subtitle_path, segment_timings


class TtsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tts"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info("tts.start", locale=ctx.locale)

        config = PipelineConfig()
        registry = VoiceRegistry(config.VOICES_DIR)
        if ctx.voice_id:
            engine, profile = registry.resolve(ctx.voice_id)
        else:
            engine, profile = registry.default_for_locale(ctx.locale)

        # Prefer storyboard narrations over the DirectStage script — the script is
        # generated before the operator may hand-edit the storyboard, so they can
        # diverge. Storyboard is always authoritative when present.
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard
            storyboard_for_script = Storyboard.load(ctx.storyboard_path)
            script_text = storyboard_for_script.derive_script()
            if ctx.script_path:
                ctx.script_path.write_text(script_text, encoding="utf-8")
        elif ctx.script_path and ctx.script_path.exists():
            script_text = ctx.script_path.read_text(encoding="utf-8")
        else:
            raise ValueError("No storyboard or script available — run direct stage first")

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
        scene_ids: list[str | None] = []
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard

            storyboard = Storyboard.load(ctx.storyboard_path)
            scene_pauses_ms = [int(s.pause_after_sec * 1000) for s in storyboard.scenes]
            # Scene ids align 1:1 with segments when the storyboard is present
            # (storyboard.derive_script emits one narration line per scene).
            scene_ids = [s.id for s in storyboard.scenes]

        # Pre-load storyboard once for per-scene narration_source dispatch.
        sb_for_dispatch = None
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard
            sb_for_dispatch = Storyboard.load(ctx.storyboard_path)

        narration_path, subtitle_path, segment_timings = await _synthesize_pass(
            segments=segments,
            scene_ids=scene_ids,
            scene_pauses_ms=scene_pauses_ms,
            audio_dir=audio_dir,
            locale_tag=ctx.locale,
            engine=engine,
            profile=profile,
            seg_prefix="segment",
            registry=registry,
            storyboard=sb_for_dispatch,
            project_root=ctx.work_dir,
        )

        ctx.narration_path = narration_path
        ctx.subtitle_path = subtitle_path
        ctx.segment_timings = segment_timings

        logger.info("tts.complete", segments=len(segments), path=str(narration_path))

        # --- Secondary (MLA) pass ---
        if ctx.secondary_locale:
            ctx = await self._run_secondary_tts(ctx, registry, audio_dir, scene_pauses_ms)

        return ctx

    async def _run_secondary_tts(
        self,
        ctx: PipelineContext,
        registry: VoiceRegistry,
        audio_dir: Path,
        scene_pauses_ms: list[int],
    ) -> PipelineContext:
        """Run a second TTS pass for secondary_locale using scene.narration_en."""
        logger.info("tts.secondary.start", locale=ctx.secondary_locale)

        if not ctx.storyboard_path or not ctx.storyboard_path.exists():
            raise ValueError(
                "Secondary TTS pass requires a storyboard — storyboard_path is not set"
            )

        from pipeline.storyboard import Storyboard

        storyboard = Storyboard.load(ctx.storyboard_path)
        scenes = storyboard.scenes

        # Collect EN narration segments; None → empty string (synthesize_pass will warn+skip).
        en_segments = [s.narration_en if s.narration_en is not None else "" for s in scenes]
        en_scene_ids = [s.id for s in scenes]

        if ctx.secondary_voice_id:
            sec_engine, sec_profile = registry.resolve(ctx.secondary_voice_id)
        else:
            sec_engine, sec_profile = registry.default_for_locale(ctx.secondary_locale)  # type: ignore[arg-type]

        sec_narration_path, sec_subtitle_path, sec_timings = await _synthesize_pass(
            segments=en_segments,
            scene_ids=en_scene_ids,
            scene_pauses_ms=scene_pauses_ms,
            audio_dir=audio_dir,
            locale_tag=ctx.secondary_locale,  # type: ignore[arg-type]
            engine=sec_engine,
            profile=sec_profile,
            seg_prefix="segment_en",
            registry=registry,
            storyboard=storyboard,
            project_root=ctx.work_dir,
        )

        ctx.secondary_narration_path = sec_narration_path
        ctx.secondary_subtitle_path = sec_subtitle_path

        # Duration checks — compare against primary segment_timings.
        primary_timings = ctx.segment_timings or []
        _check_secondary_durations(primary_timings, sec_timings, ctx.locale, ctx.secondary_locale)  # type: ignore[arg-type]

        logger.info(
            "tts.secondary.complete",
            locale=ctx.secondary_locale,
            path=str(sec_narration_path),
        )
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
    Prefers semantic break points over pure character-count midpoint:
      - before 「 (opens direct speech)    bonus 10
      - after ，/、 (natural pause)        bonus 4
      - after —— (em-dash clause boundary) bonus 14
    Returns text with actual newlines for SRT format (max 2 lines).
    """
    import re

    if _visual_width(text) <= max_width:
        return text

    tokens: list[str] = re.findall(r"[A-Za-z0-9]+|.", text)

    # Build cumulative visual widths after each token
    cum: list[int] = []
    w = 0
    for t in tokens:
        w += _visual_width(t)
        cum.append(w)
    total = w
    half = total / 2

    # Score each potential break (after token i): dist from half minus semantic bonus
    best_pos = None
    best_score = float("inf")
    for i in range(len(tokens) - 1):
        dist = abs(cum[i] - half)
        if i + 1 < len(tokens) and tokens[i + 1] == "「":
            bonus = 10
        elif tokens[i] in ("，", "、"):
            bonus = 5
        elif tokens[i] == "—" and i >= 1 and tokens[i - 1] == "—":
            bonus = 14
        else:
            bonus = 0
        score = dist - bonus
        if score < best_score:
            best_score = score
            best_pos = i

    if best_pos is not None:
        return "".join(tokens[: best_pos + 1]) + "\n" + "".join(tokens[best_pos + 1 :])

    # Fallback: greedy fill to max_width
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

    # Move leading closing-quote chars to the end of the preceding chunk.
    # Prevents orphaned 」entries from sentence-ending patterns like 。」
    fixed: list[str] = []
    for chunk in result:
        raw = chunk.replace("\n", "")
        m = re.match(r"^([」』）\]]+)(.*)", raw, re.DOTALL)
        if fixed and m:
            closing, rest = m.group(1), m.group(2).strip()
            prev = fixed[-1]
            if "\n" in prev:
                prev_lines = prev.split("\n")
                prev_lines[-1] += closing
                fixed[-1] = "\n".join(prev_lines)
            else:
                fixed[-1] = prev + closing
            if rest:
                fixed.append(_wrap_subtitle_line(rest, max_width))
        else:
            fixed.append(chunk)

    return [r for r in fixed if r]


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


def _check_secondary_durations(
    primary_timings: list[dict[str, Any]],
    secondary_timings: list[dict[str, Any]],
    primary_locale: str,
    secondary_locale: str,
) -> None:
    """Warn per scene if EN duration exceeds primary × 1.15; hard-fail if total deviation > ±2s.

    Skipped segments (narration_en was None/empty) are excluded from both checks.
    """
    total_primary_ms = 0
    total_secondary_ms = 0

    for pri, sec in zip(primary_timings, secondary_timings, strict=False):
        # Skip scenes where secondary was empty (no EN narration provided).
        if sec.get("skipped"):
            continue

        pri_dur = pri.get("duration_ms", 0)
        sec_dur = sec.get("duration_ms", 0)

        total_primary_ms += pri_dur
        total_secondary_ms += sec_dur

        # Per-scene warning: EN segment more than 15% longer than primary.
        if pri_dur > 0 and sec_dur > pri_dur * 1.15:
            logger.warning(
                "tts.secondary.scene_duration_exceed",
                scene_id=sec.get("index"),
                primary_locale=primary_locale,
                secondary_locale=secondary_locale,
                primary_ms=pri_dur,
                secondary_ms=sec_dur,
                ratio=round(sec_dur / pri_dur, 3),
            )

    # Hard-fail if total deviation exceeds ±2s.
    deviation_ms = abs(total_secondary_ms - total_primary_ms)
    if deviation_ms > 2000:
        raise ValueError(
            f"Secondary TTS ({secondary_locale}) total duration deviates from primary "
            f"({primary_locale}) by {deviation_ms / 1000:.2f}s — exceeds ±2s limit. "
            f"primary={total_primary_ms}ms secondary={total_secondary_ms}ms"
        )
