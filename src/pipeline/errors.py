from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SceneRenderError(RuntimeError):
    """A scene failed in a way that must be surfaced instead of hidden."""

    scene: str
    reason: str
    suggested_fix: str

    def __str__(self) -> str:
        return (
            f"{self.scene}: {self.reason} "
            f"Suggested fix: {self.suggested_fix}"
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "scene": self.scene,
            "reason": self.reason,
            "suggested_fix": self.suggested_fix,
        }
