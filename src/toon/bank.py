"""Resource bank: Tim's picks as data (assets/toon/bank/**.yaml) → typed, validated Bank."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Vec3 = tuple[float, float, float]


class BankError(ValueError):
    """A bank file is missing, malformed, or has fields the bank does not know."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Provenance(_Strict):
    date: str
    source: str
    note: str = ""


class Character(_Strict):
    picked: Provenance
    face: dict[str, Any]
    hair: dict[str, Any]
    body: dict[str, Any]


class Expression(_Strict):
    picked: Provenance
    eyes: Literal["dot", "wide", "closed"] = "dot"
    mouth: Literal["flat", "smile", "o", "wavy", "open"] = "flat"
    brow: float = 0.0
    worried: float = 0.0
    sweat: float = 0.0
    shock: float = 0.0
    hair: float = 0.0


class Loop(_Strict):
    hand: Literal["l", "r"]
    radius: tuple[float, float]
    hz: float


class PoseDef(_Strict):
    picked: Provenance
    hip: Literal["sit", "stand"]
    lean: float = 0.0
    head_tilt: float = 0.0
    head_turn: float = 0.0
    hand_l: Vec3
    hand_r: Vec3
    foot_l: Vec3
    foot_r: Vec3
    typing: float = 0.0
    tapping: float = 0.0
    tremble: float = 0.0
    kick: float = 0.0
    loop: Loop | None = None


class Spot(_Strict):
    pos: Vec3
    yaw: float = 0.0


class SetDef(_Strict):
    picked: Provenance
    kind: Literal["office", "kitchen"]
    spots: dict[str, Spot]


class PropDef(_Strict):
    picked: Provenance
    kind: Literal["idea_bulb", "plate", "plate_stack"]
    layer: Literal["mid", "char", "top"]
    anchor: Vec3 = (0.0, 0.0, 0.0)  # offset from the head (on:) or the hands' midpoint (held_by:)


class Punch(_Strict):
    to: float
    at: float
    over: float


class CameraPreset(_Strict):
    picked: Provenance
    az: float
    el: float
    dist: float
    target: Vec3
    focal: float                    # 1080p pixels
    focal_to: float | None = None   # eased (smooth) across the shot
    az_to: float | None = None
    punch: Punch | None = None


class Boil(_Strict):
    mode: Literal["full", "soft", "still"]
    shimmer: float = Field(ge=0.0, le=1.0)


class Style(_Strict):
    picked: Provenance
    line: dict[str, Any]
    boil: Boil
    palette: dict[str, Vec3]
    grain: float
    fps: int
    drawing_fps: int


class Bank(_Strict):
    root: Path
    characters: dict[str, Character]
    expressions: dict[str, Expression]
    poses: dict[str, PoseDef]
    sets: dict[str, SetDef]
    props: dict[str, PropDef]
    cameras: dict[str, CameraPreset]
    style: Style


def default_root() -> Path:
    env = os.environ.get("TOON_ASSETS")
    base = Path(env) if env else Path(__file__).resolve().parents[2] / "assets" / "toon"
    return base / "bank"


def _read(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise BankError(f"{path}: cannot read ({exc})") from exc


def _parse(model: type[BaseModel], data: Any, where: str) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise BankError(f"{where}: {loc}: {first['msg']}") from exc


def _dir(root: Path, sub: str, model: type[BaseModel]) -> dict[str, Any]:
    return {f.stem: _parse(model, _read(f), str(f)) for f in sorted((root / sub).glob("*.yaml"))}


def _table(root: Path, name: str, model: type[BaseModel]) -> dict[str, Any]:
    path = root / name
    data = _read(path) or {}
    if not isinstance(data, dict):
        raise BankError(f"{path}: expected a mapping of name -> entry")
    return {k: _parse(model, v, f"{path.name}:{k}") for k, v in data.items()}


def load_bank(root: Path | None = None) -> Bank:
    root = root or default_root()
    if not root.is_dir():
        raise BankError(f"bank not found at {root}")
    return Bank(
        root=root,
        characters=_dir(root, "characters", Character),
        expressions=_table(root, "expressions.yaml", Expression),
        poses=_table(root, "poses.yaml", PoseDef),
        sets=_dir(root, "sets", SetDef),
        props=_dir(root, "props", PropDef),
        cameras=_table(root, "cameras.yaml", CameraPreset),
        style=_parse(Style, _read(root / "style.yaml"), "style.yaml"),
    )


def bank_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.yaml"))
