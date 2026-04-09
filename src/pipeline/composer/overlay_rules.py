from __future__ import annotations


class OverlayCollisionError(ValueError):
    """Raised when a scene overlay would collide with subtitles or text visuals."""


_TEXT_VISUALS = {"text_card", "slide"}
_FORBIDDEN_OVERLAY_TYPES = {"text"}  # legacy name, bottom-anchored


def check_overlay_allowed(
    *,
    scene: dict,
    overlay: dict | None,
    visual: dict,
    burn_subtitles: bool,
) -> None:
    """Raise if this overlay + visual combination is unsafe.

    Rules:
    - The legacy ``text`` overlay type is banned (it anchors to the bottom
      third and collides with burned subtitles).
    - ``text_*`` overlays cannot be applied to ``text_card`` or ``slide``
      visuals (text-on-text is unreadable).
    - ``title`` and ``namecard`` overlays are allowed anywhere.
    """
    if overlay is None:
        return

    overlay_type = overlay.get("type")
    if overlay_type in _FORBIDDEN_OVERLAY_TYPES:
        raise OverlayCollisionError(
            f"scene {scene.get('id', '?')}: overlay type {overlay_type!r} is forbidden "
            "(collides with burned subtitles). Use text_top, text_left, or text_emphasis."
        )

    if overlay_type and overlay_type.startswith("text"):
        if visual.get("type") in _TEXT_VISUALS:
            raise OverlayCollisionError(
                f"scene {scene.get('id', '?')}: cannot apply {overlay_type!r} overlay to "
                f"{visual.get('type')!r} visual (text-on-text is unreadable)."
            )
