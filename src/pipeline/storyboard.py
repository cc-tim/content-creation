from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Transition:
    """A transition between two adjacent scenes.

    JSON uses 'from' and 'to' keys (Python keyword conflict is the reason
    the dataclass fields are named from_scene/to_scene).
    """

    from_scene: str
    to_scene: str
    style: str  # none | fade | page-turn | slide | wipe
    duration_sec: float
    sfx: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transition:
        return cls(
            from_scene=data["from"],
            to_scene=data["to"],
            style=data["style"],
            duration_sec=float(data["duration_sec"]),
            sfx=data.get("sfx"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "from": self.from_scene,
            "to": self.to_scene,
            "style": self.style,
            "duration_sec": self.duration_sec,
        }
        if self.sfx is not None:
            out["sfx"] = self.sfx
        return out


@dataclass
class Scene:
    id: str
    section: str  # hook | context | rising | climax | aftermath | analysis | content | punchline
    narration: str
    narration_est_sec: float
    facts_ref: list[str] = field(default_factory=list)
    visual: dict[str, Any] = field(default_factory=dict)
    overlay: dict[str, Any] | None = None
    pause_after_sec: float = 0
    compartment: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        return cls(
            id=data["id"],
            section=data["section"],
            narration=data["narration"],
            narration_est_sec=data["narration_est_sec"],
            facts_ref=list(data.get("facts_ref", [])),
            visual=dict(data.get("visual", {})),
            overlay=data.get("overlay"),
            pause_after_sec=float(data.get("pause_after_sec", 0)),
            compartment=data.get("compartment"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "section": self.section,
            "narration": self.narration,
            "narration_est_sec": self.narration_est_sec,
            "facts_ref": self.facts_ref,
            "visual": self.visual,
            "overlay": self.overlay,
            "pause_after_sec": self.pause_after_sec,
        }
        if self.compartment is not None:
            out["compartment"] = self.compartment
        return out


@dataclass
class Theme:
    """Visual theme for consistent look across all scenes."""

    background: str = "#1e293b"  # slate-800
    text_color: str = "#f8fafc"  # slate-50
    accent: str = "#38bdf8"  # sky-400
    secondary_bg: str = "#334155"  # slate-700
    font: str = "Noto Sans CJK TC"
    image_style: str = "flat minimalist illustration, simple clean lines, limited color palette"
    visual_style: str = ""  # per-video style override; takes priority over niche template

    def to_dict(self) -> dict[str, str]:
        return {
            "background": self.background,
            "text_color": self.text_color,
            "accent": self.accent,
            "secondary_bg": self.secondary_bg,
            "font": self.font,
            "image_style": self.image_style,
            "visual_style": self.visual_style,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Theme:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Storyboard:
    """Layer 2: Scene-by-scene directing. Regenerable, A/B testable."""

    version: int = 1
    format: str = "standard"  # standard | short
    target_duration_sec: int = 720
    aspect_ratio: str = "16:9"  # 16:9 | 9:16
    scenes: list[Scene] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    title: str | None = None
    description: str | None = None

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": self.version,
            "format": self.format,
            "target_duration_sec": self.target_duration_sec,
            "aspect_ratio": self.aspect_ratio,
            "theme": self.theme.to_dict(),
            "scenes": [s.to_dict() for s in self.scenes],
        }
        if self.title is not None:
            out["title"] = self.title
        if self.description is not None:
            out["description"] = self.description
        if self.transitions:
            out["transitions"] = [t.to_dict() for t in self.transitions]
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Storyboard:
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        theme_data = data.get("theme", {})
        theme = Theme.from_dict(theme_data) if theme_data else Theme()
        transitions = [Transition.from_dict(t) for t in data.get("transitions", [])]
        return cls(
            version=data.get("version", 1),
            format=data.get("format", "standard"),
            target_duration_sec=data.get("target_duration_sec", 720),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            scenes=scenes,
            theme=theme,
            title=data.get("title"),
            description=data.get("description"),
            transitions=transitions,
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> Storyboard:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # --- Script Derivation ---

    def derive_script(self) -> str:
        """Produce clean narration text for TTS.

        Concatenates scene narration with section markers that TTS
        can filter out. This replaces the old script.md format.
        """
        lines: list[str] = []
        for scene in self.scenes:
            # Section marker (TTS filters these out)
            lines.append(f"[{scene.section.upper()}]")
            lines.append("")
            # Narration text
            lines.append(scene.narration)
            lines.append("")
            # Pause marker if needed
            if scene.pause_after_sec > 0:
                lines.append(f"[PAUSE:{int(scene.pause_after_sec)}s]")
                lines.append("")
        return "\n".join(lines)

    # --- Scene Management ---

    def get_scene(self, scene_id: str) -> Scene | None:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        return None

    def swap_visual(self, scene_id: str, new_visual: dict[str, Any]) -> bool:
        """Swap the visual type for a scene. Returns True if found."""
        scene = self.get_scene(scene_id)
        if scene is None:
            return False
        scene.visual = new_visual
        return True

    def estimated_duration_sec(self) -> float:
        """Sum of narration estimates + pauses."""
        return sum(s.narration_est_sec + s.pause_after_sec for s in self.scenes)
