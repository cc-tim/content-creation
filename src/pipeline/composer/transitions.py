"""Per-seam transition primitives for the compose pipeline.

A transition is a short clip rendered between scene N and scene N+1.
Storyboards declare transitions sparsely in the `transitions[]` array;
missing entries mean a hard cut.

v1 implementation uses ffmpeg's built-in `xfade` filter for all visual
styles. The `page-turn` style is initially aliased to `xfade slideleft`
— a slide-style approximation. The Protocol abstraction allows swapping
to a PNG/webm `OverlayRenderer` later behind the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pipeline.storyboard import Transition

SUPPORTED_STYLES: set[str] = {"none", "fade", "page-turn", "slide", "wipe"}


@dataclass(frozen=True)
class TransitionConfig:
    """Render-ready config for one transition between two scenes."""

    style: str
    duration_sec: float
    sfx: str | None

    def __post_init__(self) -> None:
        if self.style not in SUPPORTED_STYLES:
            raise ValueError(
                f"Unknown transition style: {self.style!r}. "
                f"Supported: {sorted(SUPPORTED_STYLES)}"
            )

    @classmethod
    def from_transition(cls, t: Transition) -> TransitionConfig:
        return cls(style=t.style, duration_sec=t.duration_sec, sfx=t.sfx)


class TransitionRenderer(Protocol):
    """Protocol implemented by each per-style renderer.

    Implementations should be deterministic: same inputs -> same output bytes.
    The cache layer above relies on this.
    """

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        """Render the transition clip between scene_a and scene_b to `out`.

        Returns the output path on success, or None if no clip should be
        emitted (e.g. for HardCutRenderer — concat just stitches the two
        scenes directly).
        """
        ...


class HardCutRenderer:
    """Emits no transition clip — the master concat stitches scenes directly."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        return None
