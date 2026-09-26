"""The one place that loads cairo: cairocffi, with a macOS Homebrew fallback.

cairocffi dlopens libcairo at import; on macOS Homebrew's /opt/homebrew/lib is not on the
default search path, so teach ctypes.util.find_library to look there first-miss.
"""
from __future__ import annotations

import ctypes.util
import sys
from pathlib import Path

_BREW_DIRS = (Path("/opt/homebrew/lib"), Path("/usr/local/lib"))


def _patch_find_library() -> None:
    original = ctypes.util.find_library

    def find_library(name: str) -> str | None:
        found = original(name)
        if found:
            return found
        for d in _BREW_DIRS:
            for cand in (d / f"lib{name}.dylib", d / f"lib{name}.2.dylib"):
                if cand.exists():
                    return str(cand)
        return None

    ctypes.util.find_library = find_library


if sys.platform == "darwin":
    _patch_find_library()

import cairocffi as cairo  # noqa: E402

__all__ = ["cairo"]
