"""A character's explicit look (face/hair/body option dicts) -- replaces the FACE/HAIR/BODY
globals in RIG (rig_r4.py). Defaults ported verbatim from RIG 541-549 (Tim's frozen round-4
look); a scene builds a `Look` per character instead of mutating module globals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from toon.engine.palette import SHIRT

FACE_DEFAULT: dict[str, Any] = dict(eye="oval", eye_x=0.34, eye_y=-0.03, eye_s=1.0, glasses_r=0.19, glasses_fill=None,
                    temple="full", ear=False, brow="arc", brow_dy=0.27, mouth="smile", mouth_y=-0.40,
                    nose=None, blush="strokes", blush_y=-0.21, bags=False,
                    glasses_rx=None, glasses_ry=None, glasses_flat=0.0, glasses_wk=0.5, ear_r=0.16, ear_y=None,
                    jaw=0.0, lid=False, lips=False, brow_half=None, brow_wk=None, brow_tilt=0.0,
                    skin=None, glasses=True, lashes=False, mane=None, animal_ears=None, muzzle=False)
# a hair preset is one layer, or {"layers": [...]} drawn in order (e.g. buzzed sides, then the top)
HAIR_DEFAULT: dict[str, Any] = dict(fringe="saw", line=(0.42, 0.30, -0.25), spike_len=0.25, spike_deg=24, spike_irr=0.0,
                    spike_lean=0.6, top_only=False, bumps=(), fill="ink", wk=0.9, fringe_k=1.0)
BODY_DEFAULT: dict[str, Any] = {"shirt": SHIRT, "hood": False, "apron": False}


@dataclass(frozen=True)
class Look:
    face: dict[str, Any] = field(default_factory=dict)
    hair: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
