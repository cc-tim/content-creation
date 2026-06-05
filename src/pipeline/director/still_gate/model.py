from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Finding:
    """One render-truth defect found on a composited still.

    Mirrors the storyboard_validator issue shape so the decision table can
    render gate findings uniformly. `check` is the registry key that produced
    it; `suggested_fix` is always populated (lint convention).
    """

    scene_id: str
    check: str
    severity: Severity
    message: str
    suggested_fix: str
