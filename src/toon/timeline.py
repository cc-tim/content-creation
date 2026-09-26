"""What every character, prop and graphic is doing at time t. Pure: same inputs → same state."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from toon.bank import Bank
from toon.engine.mathx import EASES, V, e_out, lerp, smooth
from toon.engine.rig import HIP_SIT, HIP_STAND, Pose, mix
from toon.scene import Beat, Flicker, Show, ToonScene, graphic_key, shot_length

HIP_REF = {"sit": HIP_SIT, "stand": HIP_STAND}
POP = 0.25


@dataclass
class CharState:
    name: str
    character: str
    pose: Pose
    pose_name: str
    expr_name: str
    hip_ref: str
    root: np.ndarray
    yaw: float
    layer: str
    loop: bool


@dataclass
class PropState:
    name: str
    kind: str
    layer: str
    anchor: tuple
    on: str | None
    held_by: str | None
    b: float = 1.0
    count: int = 0
    mode: str = "on"
    smoke: float = 0.0
    blink: float | None = None


@dataclass
class GraphicState:
    key: str
    show: Show
    k: float


@dataclass
class CamState:
    az: float
    el: float
    dist: float
    target: tuple
    focal: float


@dataclass
class FrameState:
    shot: int
    set_id: str
    door: float
    cam: CamState
    chars: dict[str, CharState] = field(default_factory=dict)
    props: dict[str, PropState] = field(default_factory=dict)
    graphics: list[GraphicState] = field(default_factory=list)
    fx: list = field(default_factory=list)


def pose_of(bank: Bank, pose_name: str, expr_name: str) -> Pose:
    d, e = bank.poses[pose_name], bank.expressions[expr_name]
    return Pose(lean=d.lean, head_tilt=d.head_tilt, head_turn=d.head_turn,
                hand_l=tuple(d.hand_l), hand_r=tuple(d.hand_r),
                foot_l=tuple(d.foot_l), foot_r=tuple(d.foot_r),
                typing=d.typing, tapping=d.tapping, tremble=d.tremble, kick=d.kick,
                brow=e.brow, worried=e.worried, hair=e.hair, sweat=e.sweat, shock=e.shock,
                eyes=e.eyes, mouth=e.mouth)


def shot_index(scene: ToonScene, t: float) -> int:
    return max(i for i, sh in enumerate(scene.shots) if sh.at <= max(t, 0.0))


def _progress(b: Beat, rel: float) -> float | None:
    at = float(b.at)  # SentenceAnchor is resolved to a float before state_at ever runs
    if rel < at:
        return None
    k = 1.0 if b.over <= 0 else min((rel - at) / b.over, 1.0)
    return EASES[b.ease](k)


def state_at(scene: ToonScene, bank: Bank, t_draw: float, t_cam: float | None = None) -> FrameState:
    t_cam = t_draw if t_cam is None else t_cam
    i = shot_index(scene, t_cam)
    shot = scene.shots[i]
    t_draw = max(t_draw, shot.at)
    rel = t_draw - shot.at
    spots = bank.sets[shot.set].spots

    chars = {}
    for who, pl in shot.place.items():
        sp = spots[pl.spot]
        chars[who] = CharState(who, scene.cast[who], pose_of(bank, pl.pose, pl.expr), pl.pose, pl.expr,
                               bank.poses[pl.pose].hip, V(*sp.pos), sp.yaw, pl.layer, pl.loop)
    props = {}
    for name, pu in shot.props.items():
        d = bank.props[pu.kind]
        props[name] = PropState(name, d.kind, d.layer, tuple(d.anchor), pu.on, pu.held_by,
                                1.0 if pu.b is None else pu.b, pu.count or 0)
    door = 0.0
    graphics: dict[str, GraphicState] = {}
    flickers: dict[str, Flicker | None] = {}
    preset = bank.cameras[shot.camera]

    for b in sorted(shot.beats, key=lambda x: x.at):
        k = _progress(b, rel)
        if k is None:
            continue
        v, at = b.verb, float(b.at)
        if v == "door":
            door = lerp(door, 1.0 if b.door == "open" else 0.0, k)
        elif v == "move":
            c, dest = chars[b.move], spots[b.to]
            c.root = lerp(c.root, V(*dest.pos), k) + V(0, b.bob * abs(math.sin(k * 9)), 0)
            c.yaw = lerp(c.yaw, dest.yaw, k)
        elif v == "face":
            c, o = chars[b.face], chars[b.to]
            c.yaw = lerp(c.yaw, math.degrees(math.atan2(o.root[0] - c.root[0], o.root[2] - c.root[2])), k)
        elif v == "pose":
            c = chars[b.pose]
            to_pose, to_expr = b.to or c.pose_name, b.expr or c.expr_name
            c.pose = mix(c.pose, pose_of(bank, to_pose, to_expr), k)
            if k >= 1.0:
                c.pose_name, c.expr_name = to_pose, to_expr
        elif v == "prop":
            s = props[b.prop]
            if isinstance(b.to, dict):
                for key, val in b.to.items():
                    cur = getattr(s, key)
                    if key == "count":
                        s.count = int(cur + math.trunc((val - cur) * k))
                    else:
                        setattr(s, key, lerp(cur, val, k))
            if b.flicker is not None:
                flickers[b.prop] = b.flicker if isinstance(b.flicker, Flicker) else (Flicker() if b.flicker else None)
            if b.blink is not None and rel < at + b.blink.over:
                s.blink = b.blink.b
            if b.out:
                s.mode, s.smoke = "out", rel - at
        elif v == "show":
            dur = b.over if b.over > 0 else POP
            key = graphic_key(b.show)
            graphics[key] = GraphicState(key, b.show, min((rel - at) / dur, 1.0))
        elif v == "hide":
            graphics.pop(b.hide, None)
        elif v == "camera":
            preset = bank.cameras[b.camera]

    idx = math.floor(t_draw * bank.style.drawing_fps + 1e-9)
    for name, s in props.items():
        f = flickers.get(name)
        if s.mode != "out" and f is not None:
            s.mode, s.b = "flicker", (f.low if idx % f.every == 0 else f.high)
        if s.blink is not None and s.mode != "out":
            s.b = s.blink

    for c in chars.values():  # gesture loops (e.g. scrubbing) ride on the current pose
        loop = bank.poses[c.pose_name].loop
        if c.loop and loop is not None:
            ph = t_draw * 2 * math.pi * loop.hz
            attr = f"hand_{loop.hand}"
            x, y, z = getattr(c.pose, attr)
            c.pose = replace(c.pose, **{attr: (x + loop.radius[0] * math.cos(ph), y + loop.radius[1] * math.sin(ph), z)})

    length = shot_length(scene, i)
    rel_cam = t_cam - shot.at
    ks = smooth(rel_cam / length) if math.isfinite(length) and length > 0 else 0.0
    focal = lerp(preset.focal, preset.focal_to if preset.focal_to is not None else preset.focal, ks)
    az = lerp(preset.az, preset.az_to if preset.az_to is not None else preset.az, ks)
    if preset.punch is not None:
        pk = e_out(min(max((rel_cam - preset.punch.at) / preset.punch.over, 0.0), 1.0))
        focal = lerp(focal, preset.punch.to, pk)
    cam = CamState(az, preset.el, preset.dist, tuple(preset.target), focal)
    return FrameState(i, shot.set, door, cam, chars, props, list(graphics.values()), list(shot.fx))
