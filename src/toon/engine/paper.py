"""Paper compositing: lay the inked (transparent) cairo surface onto grained paper.

Ported from RIG (rig_r4.py) 1402-1430, made resolution-aware: `grain()` is cached per
(width, height) instead of module-global at a fixed W/H, and `composite` takes an explicit
`grain_strength` instead of reading it off a named style.
"""
import numpy as np
from PIL import Image

from toon.engine.palette import PAPER

_GRAIN: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}


def grain(width: int, height: int):
    key = (width, height)
    if key not in _GRAIN:
        rng = np.random.default_rng(7)
        fine = rng.random((height, width), dtype=np.float32)
        small = (rng.random((max(1, height // 12), max(1, width // 12))) * 255).astype(np.uint8)
        blot = np.asarray(Image.fromarray(small).resize((width, height), Image.BICUBIC), np.float32) / 255
        _GRAIN[key] = (0.7 * fine + 0.3 * blot, blot)
    return _GRAIN[key]


def composite(surf, width: int, height: int, grain_strength: float) -> np.ndarray:
    g, blot = grain(width, height)
    buf = np.frombuffer(surf.get_data(), np.uint8).reshape(height, surf.get_stride() // 4, 4)[:, :width]
    buf = buf.astype(np.float32) / 255
    a = buf[..., 3]
    k = 1 - grain_strength * g
    paper = np.array(PAPER[::-1], np.float32)[None, None, :] * (1 - 0.045 * blot)[..., None]
    out = paper * (1 - a * k)[..., None] + buf[..., :3] * k[..., None]
    bgra = np.empty((height, width, 4), np.uint8)
    bgra[..., :3] = np.clip(out * 255, 0, 255)
    bgra[..., 3] = 255
    return bgra
