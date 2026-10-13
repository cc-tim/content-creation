"""Toy3D bank v0 (E11): Tim's frozen picks from the r7-3d snapshot as YAML → a typed `Toy3DBank` →
its `SceneCatalog`.

Python validates everything it reads: the acting (poses, expressions), spots, cameras, the engine
programs' constants and the look. The page gets the resolved bank as JSON and reads the rest (the
builders' palettes and geometry, `palette:` / `params:`); it fails `init` on a key it never reads
or one it misses, so builder data can't be silently ignored either.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator

from toon.catalog import TOY3D, Catalog
from toon.scene import Ease

Vec3 = tuple[float, float, float]


class BankError(ValueError):
    """A toy3d bank file is missing, malformed, or has a field the bank does not know."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


def _colour(v: str) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}|rgba?\(\s*[0-9.]+(\s*,\s*[0-9.]+){2,3}\s*\)", v):
        raise ValueError(f"not a colour: {v!r} (#rrggbb or rgb()/rgba())")
    return v


Colour = Annotated[str, AfterValidator(_colour)]


class Provenance(_Strict):
    date: str
    source: str
    note: str = ""


# -- acting (P2-R1): poses blend their channels; loops ride inside the pose; accents add after --

class Loop(_Strict):
    channel: str
    wave: Literal["sin", "abs_sin"]
    amp: float
    rate: float                       # rad/s, at absolute scene time
    phase: float = 0.0
    until_next: Literal["stop"] | None = None   # stop at the next full pose change


class UntilNext(_Strict):
    fade: float = Field(ge=0)         # fade out over this many seconds from the next full pose


class HalfSine(_Strict):
    type: Literal["half_sine"]
    channel: str
    amp: float
    span: tuple[float, float]         # amp · sin(π · seg(since, a, b))


class Bump(_Strict):
    type: Literal["bump"]
    channels: dict[str, float]        # amplitude per channel
    at: tuple[float, ...]             # Gaussian centres (s after the beat)
    width: float = Field(gt=0)        # amp · exp(-((since - at) / width)²)


class DecaySine(_Strict):
    type: Literal["decay_sine"]
    channel: str
    amp: float
    start: float                      # u = since - start > 0: amp · e^(-decay·u) · sin(freq·u)
    decay: float
    freq: float


class Flap(_Strict):
    type: Literal["flap"]
    channel: str
    amp: float
    start: float                      # amp · sin((since-start)·2π·hz) · seg(start, start+.06) · (1 - seg(end-.25, end))
    end: float
    hz: float


class Hold(_Strict):
    type: Literal["hold"]
    channel: str
    amp: float
    after: float = 0.0                # on once since > after
    fade: tuple[float, float] | None = None


class Osc(_Strict):
    type: Literal["osc"]
    channel: str
    wave: Literal["sin", "abs_sin"]
    amp: float
    rate: float
    phase: float = 0.0
    after: float | None = None        # on once since > after
    fade: tuple[float, float] | None = None
    until_next: UntilNext | None = None


Accent = Annotated[HalfSine | Bump | DecaySine | Flap | Hold | Osc, Field(discriminator="type")]


class Flag(_Strict):
    name: str
    from_: float = Field(0.0, alias="from")


class Pose(_Strict):
    class_: Literal["sit", "stand"] = Field(alias="class")
    partial: bool = False             # a partial pose sets only its own channels
    channels: dict[str, float] = {}
    loops: tuple[Loop, ...] = ()
    accents: tuple[Accent, ...] = ()
    flags: tuple[Flag, ...] = ()


class PoseFile(_Strict):
    picked: Provenance
    poses: dict[str, Pose]


class Sweat(_Strict):
    appear: tuple[float, float]       # pops in (e_back) over this window after the expression starts
    fall: tuple[float, float]         # then slides down (e_out) over this one
    y0: float
    dy: float


class Expression(_Strict):
    decal: str | None = None          # a face decal drawn by code (web/engine/faces.js)
    sweat: Sweat | None = None


class ExpressionFile(_Strict):
    picked: Provenance
    expressions: dict[str, Expression]


# -- characters and their engine programs (P2-R2): code in toy3d.acting, constants here --

class Rig(_Strict):
    kind: Literal["tim", "lioness", "guoguo"]
    channels: tuple[str, ...]


class Walk(_Strict):
    stride: float
    bob: float
    sway: float
    hip_swing: float
    knee: float
    arm_swing: float
    settle: float


class GuoLook(_Strict):
    seat_yaw: float
    body_share: float
    head_clamp: float


class GuoSquash(_Strict):
    sq: float
    speed: float
    speed_full: float
    land: float
    wob: float


class GuoFlippers(_Strict):
    flap: float
    jig: float
    raise_: float = Field(alias="raise")


class GuoPush(_Strict):
    base: float
    speed: float
    land: float
    wob: float
    whip: float
    whip_threshold: float


class GuoEyes(_Strict):
    eye: float
    pupil: float


class GuoActing(_Strict):
    hop_scale: dict[Literal["sit", "stand"], float]
    look: GuoLook
    squash: GuoSquash
    flippers: GuoFlippers
    fur_push: GuoPush
    wide_eyes: GuoEyes


class Character(_Strict):
    picked: Provenance
    rig: Rig
    seat_height: float | None = None
    scale: float = 1.0
    walk: Walk | None = None
    guoguo: GuoActing | None = None
    palette: dict[str, Colour] = {}
    params: dict[str, Any] = {}       # the builder's geometry picks (the page reads every key)


# -- the set, props, graphics, cameras, look --

class Spot(_Strict):
    pos: Vec3
    yaw: float = 0.0                  # degrees, for placement (a toy3d move never turns: P2-R5)
    seat: Literal["chair"] | None = None


class Dust(_Strict):
    span: tuple[float, float]         # k = seg(since the open, a, b)
    grow: tuple[float, float]         # each puff's scale · (a + b · e_out(k)), drifting e_out(k) along
    alpha: float                      # opacity · (1 - k)


class Door(_Strict):
    open: float                       # radians: the swing on the door beat (its ease)…
    rest: float                       # …then a spring: rest + (open - rest)·e^(-decay·u)·cos(freq·u)
    decay: float
    freq: float
    dust: Dust                        # the puffs an open kicks up


class Laptop(_Strict):
    spot: str                         # the code bars fill while the actor here holds a `typing` pose
    lines: int
    rate: float
    max_lines: int
    cursor_rate: float


class SetDef(_Strict):
    picked: Provenance
    spots: dict[str, Spot]
    door: Door
    laptop: Laptop
    palette: dict[str, Colour] = {}
    params: dict[str, Any] = {}

    @model_validator(mode="after")
    def _laptop_spot(self):
        if self.laptop.spot not in self.spots:
            raise ValueError(f"laptop.spot {self.laptop.spot!r} is not one of the set's spots")
        return self


class BulbDrift(_Strict):
    bob: float
    bob_rate: float
    tilt: float
    tilt_rate: float


class Sway(_Strict):
    amp: float
    rate: float
    phase_step: float                 # puff i sways at phase i · phase_step


class BulbOut(_Strict):
    over: float                       # dead = e_out(seg(since out, 0, over))
    droop: float                      # the bulb sinks droop · dead…
    tilt: float                       # …and tips tilt · dead
    smoke: int                        # puffs, each k_i = seg(since out, stagger·i, smoke_span + stagger·i)
    stagger: float
    smoke_span: float
    rise: tuple[float, float]         # puff height above the bulb: a + b·k
    grow: tuple[float, float]         # puff scale · (a + b·k)
    alpha: float                      # opacity · (1 - k)
    sway: Sway


class BulbGlow(_Strict):
    base: float
    amp: float
    rate: float


class BulbRays(_Strict):
    amp: float
    rate: float
    min_level: float


class PropDef(_Strict):
    picked: Provenance
    kind: Literal["idea_bulb"]
    anchor: Vec3
    drift: BulbDrift
    out: BulbOut
    glow: BulbGlow
    rays: BulbRays
    lit_min: float                    # the glass reads lit above this level
    palette: dict[str, Colour] = {}
    params: dict[str, Any] = {}


class Offset(_Strict):
    right: float
    up: float


class Wave(_Strict):
    amp: float
    rate: float


class Pop(_Strict):
    scale: float


class Bang(_Strict):
    signal: str


class Bubble(_Strict):
    picked: Provenance
    icons: tuple[str, ...]
    offset: Offset
    bob: Wave
    pop: Pop
    bang: Bang
    palette: dict[str, Colour] = {}
    params: dict[str, Any] = {}


class Tween(_Strict):
    at: float
    over: float = Field(0.0, ge=0)    # 0: a cut
    ease: Ease = "linear"
    to: float | Vec3


class Track(_Strict):
    start: float | Vec3
    tweens: tuple[Tween, ...] = ()

    @model_validator(mode="after")
    def _same_kind(self):
        scalar = isinstance(self.start, float)
        for i, tw in enumerate(self.tweens):
            if isinstance(tw.to, float) != scalar:
                raise ValueError(f"tweens.{i}.to: a {'number' if scalar else '[x, y, z]'} like start")
        return self


class Orbit(_Strict):
    pivot: Track
    az: Track                         # degrees
    el: Track
    dist: Track


class CameraPreset(_Strict):
    picked: Provenance
    orbit: Orbit | None = None        # an orbiting position, or…
    pos: Vec3 | None = None           # …a fixed one
    target: Track
    fov: Track
    up: Vec3 = (0.0, 1.0, 0.0)

    @model_validator(mode="after")
    def _one_position(self):
        if (self.orbit is None) == (self.pos is None):
            raise ValueError("a camera takes exactly one of orbit: or pos:")
        return self


class Tone(_Strict):
    mapping: Literal["neutral"]
    exposure: float


class Shadows(_Strict):
    type: Literal["pcf"]


class Fog(_Strict):
    color: Colour
    near: float
    far: float


class Environment(_Strict):
    room: bool
    sigma: float
    intensity: float


class Clip(_Strict):
    near: float
    far: float


class Gtao(_Strict):
    radius: float
    distance_exponent: float
    thickness: float
    scale: float
    samples: int
    blend: float


class Denoise(_Strict):
    luma_phi: float
    depth_phi: float
    normal_phi: float
    radius: float
    rings: int
    samples: int


class Bloom(_Strict):
    strength: float
    radius: float
    threshold: float


class Grade(_Strict):
    vignette: float
    grain: float
    warm: float


class Post(_Strict):
    samples: int
    gtao: Gtao
    denoise: Denoise
    bloom: Bloom
    grade: Grade


class SoftMaterial(_Strict):
    roughness: float
    clearcoat: float
    clearcoat_roughness: float
    sheen: float
    sheen_roughness: float
    sheen_mix: float


class PropMaterial(_Strict):
    roughness: float


class FaceMaterial(_Strict):
    roughness: float


class Materials(_Strict):
    soft: SoftMaterial
    prop: PropMaterial
    face: FaceMaterial


class Style(_Strict):
    picked: Provenance
    fps: int
    size: tuple[int, int]
    tone: Tone
    shadows: Shadows
    background: Colour
    fog: Fog
    environment: Environment
    camera: Clip
    post: Post
    materials: Materials


class Toy3DBank(_Strict):
    root: Path
    style: Style
    characters: dict[str, Character]
    pose_files: dict[str, PoseFile]
    expression_files: dict[str, ExpressionFile]
    sets: dict[str, SetDef]
    cameras: dict[str, CameraPreset]
    props: dict[str, PropDef]
    bubble: Bubble
    trace: dict[str, Any]             # guo_trace.json: GuoGuo's photo traces (frozen with v7)

    @property
    def poses(self) -> dict[str, dict[str, Pose]]:
        return {c: f.poses for c, f in self.pose_files.items()}

    @property
    def expressions(self) -> dict[str, dict[str, Expression]]:
        return {c: f.expressions for c, f in self.expression_files.items()}

    @property
    def catalog(self) -> Catalog:
        """This bank's names and the toy3d engine's capabilities, for `toon.scene.load_scene`."""
        return Catalog(
            capabilities=TOY3D,
            characters=frozenset(self.characters),
            set_spots={name: frozenset(s.spots) for name, s in self.sets.items()},
            cameras=frozenset(self.cameras),
            prop_items={name: p.kind for name, p in self.props.items()},
            icons=frozenset(self.bubble.icons),
            poses={c: {name: p.class_ for name, p in poses.items()} for c, poses in self.poses.items()},
            expressions={c: frozenset(e) for c, e in self.expressions.items()},
        )


def default_root() -> Path:
    env = os.environ.get("TOY3D_ASSETS")
    base = Path(env) if env else Path(__file__).resolve().parents[2] / "assets" / "toy3d"
    return base / "bank"


def _read(root: Path, path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise BankError(f"{path.relative_to(root)}: cannot read ({' '.join(str(exc).split())})") from exc


def _parse(root: Path, model: type[BaseModel], path: Path) -> Any:
    where = path.relative_to(root)
    try:
        return model.model_validate(_read(root, path))
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise BankError(f"{where}: {loc}: {first['msg']}") from exc


def _dir(root: Path, sub: str, model: type[BaseModel]) -> dict[str, Any]:
    return {f.stem: _parse(root, model, f) for f in sorted((root / sub).glob("*.yaml"))}


def _check_rig_channels(character: str, rig: Rig, poses: PoseFile) -> None:
    """Every channel a pose sets, loops or accents must be one the character's rig has."""
    known = set(rig.channels)

    def bad(path: str, channel: str) -> None:
        if channel not in known:
            raise BankError(f"poses/{character}.yaml: poses.{path}: not a {character} rig channel "
                            f"({channel!r}; the rig has {sorted(known)})")

    for name, pose in poses.poses.items():
        for ch in pose.channels:
            bad(f"{name}.channels.{ch}", ch)
        for i, loop in enumerate(pose.loops):
            bad(f"{name}.loops.{i}.channel", loop.channel)
        for i, acc in enumerate(pose.accents):
            if isinstance(acc, Bump):
                for ch in acc.channels:
                    bad(f"{name}.accents.{i}.channels.{ch}", ch)
            else:
                bad(f"{name}.accents.{i}.channel", acc.channel)


def load_bank(root: Path | None = None) -> Toy3DBank:
    root = root or default_root()
    if not root.is_dir():
        raise BankError(f"toy3d bank not found at {root}")
    characters = _dir(root, "characters", Character)
    pose_files = _dir(root, "poses", PoseFile)
    expression_files = _dir(root, "expressions", ExpressionFile)
    for kind, files in (("poses", pose_files), ("expressions", expression_files)):
        if set(files) != set(characters):
            raise BankError(f"{kind}/: one file per character ({sorted(characters)}), got {sorted(files)}")
    for name, ch in characters.items():
        _check_rig_channels(name, ch.rig, pose_files[name])
    trace_path = root / "guo_trace.json"
    try:
        trace = json.loads(trace_path.read_text())
    except (OSError, ValueError) as exc:
        raise BankError(f"guo_trace.json: cannot read ({exc})") from exc
    return Toy3DBank(
        root=root,
        style=_parse(root, Style, root / "style.yaml"),
        characters=characters,
        pose_files=pose_files,
        expression_files=expression_files,
        sets=_dir(root, "sets", SetDef),
        cameras=_dir(root, "cameras", CameraPreset),
        props=_dir(root, "props", PropDef),
        bubble=_parse(root, Bubble, root / "graphics" / "bubble.yaml"),
        trace=trace,
    )
