"""Shared Anthropic API key resolution.

Used by every CLI module that calls the Anthropic API (proofread, mla,
storyteller, image_alignment, visual_review). Resolution order:
1. ANTHROPIC_API_KEY env var
2. PIPELINE_ANTHROPIC_API_KEY env var
3. PIPELINE_ANTHROPIC_API_KEY=... line in ./.env
"""

from __future__ import annotations

import os
from pathlib import Path


def get_anthropic_api_key() -> str:
    """Resolve the Anthropic API key. Raises RuntimeError if none found."""
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PIPELINE_ANTHROPIC_API_KEY")
    if not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("PIPELINE_ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY. Set PIPELINE_ANTHROPIC_API_KEY in .env.")
    return key
