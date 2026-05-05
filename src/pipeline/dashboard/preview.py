"""Build lightweight Telegram previews for dashboard mutation results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

PreviewKind = Literal["photo", "video", "text_diff"]


@dataclass(frozen=True)
class Preview:
    kind: PreviewKind
    path: Path | None = None
    body: str = ""
    caption: str = ""


def build_preview(
    *,
    verb: str,
    args: dict[str, Any],
    project_root: Path,
    old_text: str | None = None,
) -> Preview:
    if verb in {"subtitle set", "overlay set", "narration regen"}:
        return Preview(
            kind="text_diff",
            body=_format_text_diff(old=old_text or "", new=str(args.get("text", ""))),
        )

    if verb == "image regen":
        scene = args.get("scene")
        candidate = project_root / "images" / "scenes" / f"{scene}.png"
        if candidate.exists():
            return Preview(kind="photo", path=candidate, caption=f"image {scene} regenerated")
        return Preview(kind="text_diff", body=f"image {scene} regenerated (artifact pending)")

    if verb in {"transition set", "transition clear"}:
        from_scene = args.get("from")
        to_scene = args.get("to")
        candidate = project_root / "compose" / f"seam_{from_scene}_{to_scene}.mp4"
        if candidate.exists():
            return Preview(
                kind="video",
                path=candidate,
                caption=f"transition {from_scene} to {to_scene} preview",
            )
        return Preview(
            kind="text_diff",
            body=f"transition {from_scene} to {to_scene} updated (recompose pending)",
        )

    if verb == "narration set-source":
        return Preview(
            kind="text_diff",
            body=f"narration source for {args.get('scene')} => {args.get('engine')}",
        )

    return Preview(kind="text_diff", body=f"{verb} applied")


def _format_text_diff(*, old: str, new: str) -> str:
    return f"BEFORE: {_truncate(old)}\nAFTER:  {_truncate(new)}"


def _truncate(value: str, limit: int = 200) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
