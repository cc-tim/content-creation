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
