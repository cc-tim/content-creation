"""Colour constants and role lookup (ported from RIG 32-62 + SCN 35-37; plant not ported)."""
from __future__ import annotations

PAPER = (0.957, 0.945, 0.918)
SKIN = (0.985, 0.978, 0.960)
SHIRT = (0.50, 0.58, 0.67)
WOOD = (0.79, 0.69, 0.56)
CHAIR = (0.52, 0.50, 0.49)
METAL = (0.80, 0.80, 0.78)
SCREEN = (0.92, 0.92, 0.89)
SHADE = (0.92, 0.84, 0.62)
RUG = (0.88, 0.83, 0.75)
BLUSH = (0.84, 0.52, 0.52)
MUG = (0.70, 0.45, 0.40)
RED = (0.78, 0.30, 0.25)
GREEN = (0.36, 0.58, 0.38)
BLUE = (0.38, 0.50, 0.66)

NAVY = (0.20, 0.25, 0.36)
BUZZ = (0.36, 0.35, 0.35)
GHOST_INK = (0.72, 0.69, 0.64)

ORANGE = (0.86, 0.52, 0.28)
BULB_ON = (0.99, 0.86, 0.42)
BULB_OFF = (0.84, 0.84, 0.82)
SMOKE = (0.55, 0.53, 0.5)

ROLE = {"skin": SKIN, "shirt": SHIRT, "wood": WOOD, "chair": CHAIR, "metal": METAL,
        "screen": SCREEN, "shade": SHADE, "rug": RUG, "mug": MUG, "white": (1, 1, 1)}
