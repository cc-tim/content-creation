from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_FILENAME = "constraints.json"


@dataclass
class ProjectConstraints:
    duration_min_minutes: float | None = None
    duration_max_minutes: float | None = None
    notes: str = ""

    @classmethod
    def load(cls, work_dir: Path) -> ProjectConstraints | None:
        path = work_dir / _FILENAME
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def save(self, work_dir: Path) -> None:
        path = work_dir / _FILENAME
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def format_reminder(self) -> str:
        lines = ["PROJECT CONSTRAINTS (set at initial produce — must be preserved):"]
        lo, hi = self.duration_min_minutes, self.duration_max_minutes
        if lo is not None and hi is not None:
            lines.append(f"  - Duration: {lo}–{hi} minutes (HARD REQUIREMENT)")
        elif lo is not None:
            lines.append(f"  - Duration: at least {lo} minutes (HARD REQUIREMENT)")
        elif hi is not None:
            lines.append(f"  - Duration: at most {hi} minutes (HARD REQUIREMENT)")
        if self.notes:
            lines.append(f"  - Notes: {self.notes}")
        return "\n".join(lines)

    def duration_instruction(self) -> str:
        """Short sentence injected into the storyboard prompt structure block."""
        lo, hi = self.duration_min_minutes, self.duration_max_minutes
        if lo is not None and hi is not None:
            return f"Target {lo}–{hi} minutes total. HARD REQUIREMENT: stay within this range."
        if lo is not None:
            return f"Target at least {lo} minutes total. HARD REQUIREMENT."
        if hi is not None:
            return f"Target at most {hi} minutes total. HARD REQUIREMENT."
        return ""

    def check_storyboard(self, duration_sec: float) -> list[str]:
        """Returns list of human-readable violations. Empty list = OK."""
        violations: list[str] = []
        minutes = duration_sec / 60
        if self.duration_min_minutes is not None and minutes < self.duration_min_minutes:
            violations.append(
                f"Duration {minutes:.1f} min is below the {self.duration_min_minutes} min minimum"
            )
        if self.duration_max_minutes is not None and minutes > self.duration_max_minutes:
            violations.append(
                f"Duration {minutes:.1f} min exceeds the {self.duration_max_minutes} min maximum"
            )
        return violations
