#!/usr/bin/env python3
"""Rewrite legacy ``text`` overlays to ``text_top`` for an existing storyboard.

Usage:
    uv run python scripts/migrate_storyboard_overlays.py output/projects/<ID>/storyboard.json

Safe to re-run — it's idempotent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate(storyboard_path: Path) -> int:
    data = json.loads(storyboard_path.read_text())
    changed = 0
    for scene in data.get("scenes", []):
        overlay = scene.get("overlay")
        if not overlay:
            continue
        if overlay.get("type") == "text":
            overlay["type"] = "text_top"
            changed += 1
        # Disallow applying text overlays to text visuals.
        if overlay.get("type", "").startswith("text"):
            v = scene.get("visual", {})
            if v.get("type") in ("text_card", "slide"):
                scene["overlay"] = None
                changed += 1
    storyboard_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    )
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    changed = migrate(path)
    print(f"migrated {changed} overlay entries in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
