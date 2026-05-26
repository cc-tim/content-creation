from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

StyleKind = Literal[
    "frame",
    "image_prompt_prefix",
    "transition",
    "theme_color",
    "seed",
    "anchor_image",
    "overlay",
]

_MEDIUM_KEYWORDS = (
    "sketch",
    "lines",
    "hand-drawn",
    "illustration",
    "watercolor",
    "painted",
    "drawing",
)


def _medium_descriptor_warnings(value: str, field_name: str) -> list[str]:
    clashing = [
        kw
        for kw in _MEDIUM_KEYWORDS
        if re.search(rf"\b{re.escape(kw)}\b", value, re.IGNORECASE)
    ]
    if not clashing:
        return []
    return [
        f"{field_name} contains medium descriptor(s) {clashing!r} that may conflict "
        "with photo-realistic generated_image prompts. The assembler suppresses "
        "medium_hint for photo-realistic scenes; use visual.skip_niche_style: true "
        "only when all niche styling must be removed."
    ]


@dataclass
class StyleElement:
    id: str
    kind: StyleKind
    value: str
    source: str         # "project_theme" | "niche:<name>" | "scene_override"
    scope: str          # "all_scenes" | "generated_image_scenes" | "all_transitions"
    theme_key: str      # which storyboard theme key to delete on `style remove`
    active: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class PerSceneOverride:
    scene_id: str
    kind: str   # "skip_niche_style" | "style_modifier"
    value: str


@dataclass
class StyleManifest:
    project_id: str
    elements: list[StyleElement]
    per_scene_overrides: list[PerSceneOverride]


def build_manifest(storyboard_path: Path) -> StyleManifest:
    """Read storyboard.json and produce a StyleManifest of all active style elements."""
    data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    project_id = data.get("project_id", storyboard_path.parent.name)
    theme = data.get("theme", {})
    scenes = data.get("scenes", [])

    elements: list[StyleElement] = []
    overrides: list[PerSceneOverride] = []

    # 1. frame_style
    if frame_val := theme.get("frame_style"):
        elements.append(
            StyleElement(
                id=f"frame_{frame_val}",
                kind="frame",
                value=frame_val,
                source="project_theme",
                scope="all_scenes",
                theme_key="frame_style",
                warnings=[
                    "No per-scene opt-out available (all-or-nothing per project). "
                    "Use `style remove` to drop the frame globally."
                ],
            )
        )

    # 2. Split niche image-prompt fields
    for theme_key, element_id in (
        ("medium_hint", "medium_hint"),
        ("palette", "palette"),
        ("subject_bias", "subject_bias"),
    ):
        if value := theme.get(theme_key):
            warnings = (
                _medium_descriptor_warnings(value, "medium_hint")
                if theme_key == "medium_hint"
                else []
            )
            elements.append(
                StyleElement(
                    id=element_id,
                    kind="image_prompt_prefix",
                    value=value,
                    source="project_theme",
                    scope="generated_image_scenes",
                    theme_key=theme_key,
                    warnings=warnings,
                )
            )

    # 3. visual_style (legacy/composite image-prompt prefix)
    if vs := theme.get("visual_style"):
        elements.append(
            StyleElement(
                id="visual_style",
                kind="image_prompt_prefix",
                value=vs,
                source="project_theme",
                scope="generated_image_scenes",
                theme_key="visual_style",
            )
        )

    # 4. intro_transition_style
    if trans := theme.get("intro_transition_style"):
        slug = trans.replace("-", "_").replace(" ", "_")
        elements.append(
            StyleElement(
                id=f"transition_{slug}",
                kind="transition",
                value=trans,
                source="project_theme",
                scope="all_transitions",
                theme_key="intro_transition_style",
            )
        )

    # 5. anchor_image (stored but never used — surfaces the no-op bug)
    if anchor := theme.get("_anchor_image"):
        elements.append(
            StyleElement(
                id="anchor_image",
                kind="anchor_image",
                value=anchor,
                source="project_theme",
                scope="generated_image_scenes",
                theme_key="_anchor_image",
                active=False,
                warnings=[
                    "anchor_image is stored but NOT used in image generation "
                    "(img2img not yet implemented). It has no effect on rendered output."
                ],
            )
        )

    # 6. Per-scene overrides
    for scene in scenes:
        sid = scene.get("id") or scene.get("scene_id", "")
        vis = scene.get("visual", {})
        if vis.get("skip_niche_style"):
            overrides.append(
                PerSceneOverride(scene_id=sid, kind="skip_niche_style", value="true")
            )
        if modifier := vis.get("style_modifier"):
            overrides.append(
                PerSceneOverride(scene_id=sid, kind="style_modifier", value=modifier)
            )

    # 7. callout overlay (aggregate-by-type): line charts with markers carry
    #    collision-placed callouts. Derived from chart data, not a theme global.
    callout_scenes = [
        (scene.get("id") or scene.get("scene_id", ""))
        for scene in scenes
        if (vis := scene.get("visual", {})).get("type") == "chart"
        and vis.get("chart_type") == "line"
        and (vis.get("data") or {}).get("markers")
    ]
    if callout_scenes:
        elements.append(
            StyleElement(
                id="callout",
                kind="overlay",
                value=f"marker callouts on {', '.join(callout_scenes)}",
                source="chart_data",
                scope="chart_line_scenes",
                theme_key="",
                warnings=[
                    "Derived from line-chart markers, not a removable theme global. "
                    "To change, edit visual.data.markers on the listed scenes."
                ],
            )
        )

    return StyleManifest(
        project_id=project_id,
        elements=elements,
        per_scene_overrides=overrides,
    )
