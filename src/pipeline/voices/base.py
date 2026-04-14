from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class VoiceNotFound(LookupError):
    """Raised when a requested voice_id does not exist in the registry."""


@dataclass
class VoiceProfile:
    id: str
    engine: str  # "edge" | "prerecorded"
    locale: str
    params: dict[str, Any] = field(default_factory=dict)
    reference_path: Path | None = None
    reference_text: str | None = None
    display_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceProfile:
        ref = data.get("reference")
        return cls(
            id=data["id"],
            engine=data["engine"],
            locale=data["locale"],
            params=dict(data.get("params") or {}),
            reference_path=Path(ref) if ref else None,
            reference_text=data.get("reference_text"),
            display_name=data.get("display_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "engine": self.engine,
            "locale": self.locale,
            "params": dict(self.params),
        }
        if self.reference_path is not None:
            out["reference"] = str(self.reference_path)
        if self.reference_text is not None:
            out["reference_text"] = self.reference_text
        if self.display_name is not None:
            out["display_name"] = self.display_name
        return out


class VoiceEngine(ABC):
    """Turns narration text into a WAV/MP3 file using a specific backend."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        """Write audio for `text` to `out_path`. Returns the final path.

        `scene_id` is the storyboard scene identifier, passed down by TtsStage.
        Engines that key off scene identity (e.g. PrerecordedEngine) use it;
        others ignore it.
        """
