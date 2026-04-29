from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

_HISTORY_DIR = "image_history"
_TS_FMT = "%Y%m%dT%H%M%S"


def _hist_dir(work_dir: Path) -> Path:
    return work_dir / _HISTORY_DIR


def save_to_history(source_png: Path, scene_id: str, work_dir: Path) -> Path:
    """Copy source_png to image_history/{scene_id}_{timestamp}.png before overwriting."""
    d = _hist_dir(work_dir)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime(_TS_FMT)
    dest = d / f"{scene_id}_{ts}.png"
    shutil.copy2(source_png, dest)
    return dest


def find_history(scene_id: str, work_dir: Path) -> list[tuple[datetime, Path]]:
    """Return (datetime, path) pairs for scene_id, most-recent first."""
    d = _hist_dir(work_dir)
    if not d.exists():
        return []
    prefix = f"{scene_id}_"
    results: list[tuple[datetime, Path]] = []
    for p in d.glob(f"{scene_id}_*.png"):
        ts_str = p.stem[len(prefix):]
        try:
            ts = datetime.strptime(ts_str, _TS_FMT)
            results.append((ts, p))
        except ValueError:
            continue
    return sorted(results, key=lambda x: x[0], reverse=True)


def purge_old(work_dir: Path, max_age_days: int = 7) -> int:
    """Delete history entries older than max_age_days. Returns count deleted."""
    d = _hist_dir(work_dir)
    if not d.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for p in d.glob("*.png"):
        if p.stat().st_mtime < cutoff:
            p.unlink()
            removed += 1
    return removed


def restore_scene(
    scene_id: str, work_dir: Path, timestamp_str: str | None = None
) -> Path | None:
    """Copy a history entry to work_dir/{scene_id}_restore.png. Returns path or None."""
    entries = find_history(scene_id, work_dir)
    if not entries:
        return None
    if timestamp_str:
        matched = [p for ts, p in entries if ts.strftime(_TS_FMT) == timestamp_str]
        if not matched:
            return None
        src = matched[0]
    else:
        _, src = entries[0]
    dest = work_dir / f"{scene_id}_restore.png"
    shutil.copy2(src, dest)
    return dest
