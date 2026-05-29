"""Background-music layer on the audio axis.

A per-scene ``music_mood`` (inherit-on-blank) resolves to per-scene effective
moods; combined with ``compose/scenes.json`` spans these become *cues*. A
full-length, 48 kHz/stereo mood bed (with crossfades at mood boundaries) is
sidechain-ducked under the pristine ``raw.mp4`` narration and amixed onto each
final video. See docs/superpowers/specs/2026-05-29-music-audio-axis-design.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg, run_ffmpeg_atomic

MUSIC_MOODS = ("tense", "somber", "hopeful", "triumphant", "reflective", "none")

_REPO_ROOT = Path(__file__).resolve().parents[3]
MUSIC_LIBRARY_JSON = _REPO_ROOT / "assets" / "music" / "library.json"

# Crossfade duration where two non-"none" cues abut; shorter fade to/from silence
# at a cue's edge against a gap or the video boundary.
_XFADE_SEC = 1.2
_EDGE_FADE_SEC = 0.8


@dataclass(frozen=True)
class MoodTrack:
    """A resolved music bed for one mood (absolute path to the audio file)."""

    mood: str
    file: Path


@dataclass(frozen=True)
class Cue:
    """A contiguous span of one (non-"none") mood on the video timeline."""

    mood: str
    start_sec: float
    end_sec: float

    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec


def resolve_effective_moods(storyboard) -> list[tuple[str, str]]:
    """Resolve each scene's *effective* mood by walking scenes in order.

    ``eff[i] = scene.music_mood or eff[i-1]``, seeded by ``theme.music_default_mood``
    (default ``"none"``). ``"none"`` is an explicit mood that propagates like any
    other. Raises ``ValueError`` on an unknown mood tag.
    """
    eff = storyboard.theme.music_default_mood or "none"
    out: list[tuple[str, str]] = []
    for sc in storyboard.scenes:
        m = sc.music_mood or ""
        if m and m not in MUSIC_MOODS:
            raise ValueError(
                f"scene {sc.id}: unknown music_mood {m!r} (allowed: {MUSIC_MOODS})"
            )
        if m:
            eff = m
        out.append((sc.id, eff))
    return out


def load_library(path: Path = MUSIC_LIBRARY_JSON) -> dict[str, MoodTrack]:
    """Load the mood -> track mapping from the library manifest.

    Entries with an empty/absent ``file`` are skipped, so a mood that has not yet
    had a real track dropped in is simply absent from the returned mapping (the
    CLI then errors clearly if that mood is actually used).
    """
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    lib: dict[str, MoodTrack] = {}
    for mood, entry in data.items():
        rel = (entry or {}).get("file")
        if rel:
            lib[mood] = MoodTrack(mood=mood, file=(path.parent / rel))
    return lib


def plan_cues(storyboard, scenes: list[dict]) -> list[Cue]:
    """Turn effective per-scene moods + scenes.json spans into cues.

    Adjacent scenes sharing a mood are merged into one cue; a ``"none"`` scene
    breaks the run (so the same mood either side of a silent gap yields two cues).
    ``scenes`` are rows from ``compose/scenes.json`` (``id``/``start_sec``/
    ``duration_sec``).
    """
    moods = dict(resolve_effective_moods(storyboard))
    rows = sorted(scenes, key=lambda s: s["start_sec"])
    cues: list[Cue] = []
    for s in rows:
        mood = moods.get(s["id"], "none")
        if mood == "none":
            continue
        start = float(s["start_sec"])
        end = start + float(s["duration_sec"])
        if cues and cues[-1].mood == mood and abs(cues[-1].end_sec - start) < 1e-2:
            cues[-1] = Cue(mood, cues[-1].start_sec, end)
        else:
            cues.append(Cue(mood, start, end))
    return cues


def build_bed(
    cues: list[Cue],
    library: dict[str, MoodTrack],
    total_sec: float,
    out_path: Path,
) -> Path | None:
    """Render the full-length mood bed (48 kHz/stereo) aligned to the timeline.

    Each cue loops its mood track, trims to the cue length, fades at the edges,
    and is placed via ``adelay``. Adjacent (abutting) cues overlap by ``_XFADE_SEC``
    so their equal-power fades crossfade; a cue against a gap/edge fades to silence
    over ``_EDGE_FADE_SEC``. Returns ``None`` when there are no cues.
    """
    if not cues:
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    eps = 1e-2
    inputs: list[str] = []
    filters: list[str] = []
    for i, c in enumerate(cues):
        track = library[c.mood].file
        left_abut = i > 0 and abs(cues[i - 1].end_sec - c.start_sec) < eps
        right_abut = i < len(cues) - 1 and abs(cues[i + 1].start_sec - c.end_sec) < eps
        place_at = max(0.0, c.start_sec - (_XFADE_SEC if left_abut else 0.0))
        seg_dur = c.end_sec - place_at
        fin = min(_XFADE_SEC if left_abut else _EDGE_FADE_SEC, seg_dur / 2)
        fout = min(_XFADE_SEC if right_abut else _EDGE_FADE_SEC, seg_dur / 2)
        delay_ms = int(round(place_at * 1000))
        inputs += ["-stream_loop", "-1", "-i", str(track)]
        filters.append(
            f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"atrim=0:{seg_dur:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fin:.3f},"
            f"afade=t=out:st={seg_dur - fout:.3f}:d={fout:.3f},"
            f"adelay={delay_ms}:all=1[c{i}]"
        )

    if len(cues) == 1:
        mix = f"[c0]apad=whole_dur={total_sec:.3f},atrim=0:{total_sec:.3f}[bed]"
    else:
        labels = "".join(f"[c{i}]" for i in range(len(cues)))
        mix = (
            f"{labels}amix=inputs={len(cues)}:normalize=0:dropout_transition=0,"
            f"apad=whole_dur={total_sec:.3f},atrim=0:{total_sec:.3f}[bed]"
        )

    fc = ";".join([*filters, mix])
    run_ffmpeg(
        ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
         "-map", "[bed]", "-ar", "48000", "-ac", "2", str(out_path)]
    )
    return out_path


def duck_bed(
    bed_path: Path,
    key_audio_path: Path,
    out_path: Path,
    duck_db: float = 15.0,
) -> Path:
    """Sidechain-duck the bed under ``key_audio`` (the narration), as a standalone
    artifact so the result is directly measurable.

    ``volume=-duck_db`` sets the bed's resting floor; ``sidechaincompress`` keyed by
    the narration adds dynamic ducking while speech is present (recovering in pauses).
    Target during speech ≈ 12-15 dB below narration. Output is 48 kHz/stereo.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fc = (
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[key];"
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=-{duck_db}dB[m];"
        "[m][key]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[duck]"
    )
    run_ffmpeg(
        ["ffmpeg", "-y", "-i", str(bed_path), "-i", str(key_audio_path),
         "-filter_complex", fc, "-map", "[duck]", "-ar", "48000", "-ac", "2", str(out_path)]
    )
    return out_path


def mux_music_onto_final(
    final_video: Path,
    narration_audio: Path,
    ducked_bed: Path,
    out_path: Path,
) -> None:
    """Mix narration + ducked bed and mux onto ``final_video`` (video stream-copied).

    The narration bus is read from ``narration_audio`` (the pristine ``raw.mp4``),
    NOT from ``final_video`` — so re-running over an already-musicked final does not
    double the music (idempotent). Written atomically over ``out_path``.
    """
    fc = (
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[n];"
        "[2:a]aformat=sample_rates=48000:channel_layouts=stereo[d];"
        "[n][d]amix=inputs=2:normalize=0:duration=first[mix]"
    )
    run_ffmpeg_atomic(
        ["ffmpeg", "-y", "-i", str(final_video), "-i", str(narration_audio),
         "-i", str(ducked_bed), "-filter_complex", fc,
         "-map", "0:v", "-c:v", "copy", "-map", "[mix]", "-c:a", "aac", "-b:a", "192k",
         str(out_path)],
        Path(out_path),
    )
