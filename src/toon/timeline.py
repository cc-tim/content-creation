"""What every character, prop and graphic is doing at time t. Pure: same inputs → same state."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from toon.bank import Bank
from toon.beats import POP as POP
from toon.beats import ActorAt as ActorAt
from toon.beats import CameraAt as CameraAt
from toon.beats import Change as Change
from toon.beats import DoorAt as DoorAt
from toon.beats import GraphicAt as GraphicAt
from toon.beats import PropAt as PropAt
from toon.beats import SymbolicState as SymbolicState
from toon.beats import beats_at
from toon.engine.mathx import V, e_out, lerp, smooth
from toon.engine.rig import HIP_SIT, HIP_STAND, Pose, mix
from toon.scene import Show, ToonScene

HIP_REF = {"sit": HIP_SIT, "stand": HIP_STAND}


class ToonRenderError(RuntimeError):
    pass


def require_toon2d(scene: ToonScene) -> None:
    """The 2.5D engine draws toon2d scenes only: a toy3d scene is never drawn as a doodle."""
    if scene.engine != "toon2d":
        raise ToonRenderError(f"{scene.id}: a {scene.engine} scene; the 2.5D engine draws toon2d scenes")


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


def state_at(scene: ToonScene, bank: Bank, t_draw: float, t_cam: float | None = None) -> FrameState:
    """The 2.5D engine's frame: the symbolic timeline folded over this bank's spots, poses,
    props and cameras, with flicker on drawings (twos) and gesture loops."""
    require_toon2d(scene)
    sym = beats_at(scene, t_draw, t_cam)
    spots = bank.sets[sym.set].spots

    chars = {}
    for a in sym.actors:
        sp = spots[a.spot]
        chars[a.name] = CharState(a.name, a.character, pose_of(bank, a.pose, a.expr), a.pose, a.expr,
                                  bank.poses[a.pose].hip, V(*sp.pos), sp.yaw, a.layer or "split",
                                  True if a.loop is None else a.loop)
    for ch in sym.changes:
        c, k = chars[ch.who], ch.k
        if ch.verb == "move":
            dest = spots[ch.to]
            c.root = lerp(c.root, V(*dest.pos), k) + V(0, (ch.bob or 0.0) * abs(math.sin(k * 9)), 0)
            c.yaw = lerp(c.yaw, dest.yaw, k)
        elif ch.verb == "face":
            o = chars[ch.to]
            c.yaw = lerp(c.yaw, math.degrees(math.atan2(o.root[0] - c.root[0], o.root[2] - c.root[2])), k)
        else:  # pose
            c.pose = mix(c.pose, pose_of(bank, ch.to, ch.expr), k)
            if k >= 1.0:
                c.pose_name, c.expr_name = ch.to, ch.expr

    idx = math.floor(sym.t_draw * bank.style.drawing_fps + 1e-9)
    props = {}
    for p in sym.props:
        d = bank.props[p.item]
        s = PropState(p.name, d.kind, d.layer, tuple(d.anchor), p.on, p.held_by, p.b, p.count,
                      p.mode, p.smoke, p.blink)
        if s.mode != "out" and p.flicker is not None:  # a flicker toggles per drawing (twos)
            s.mode, s.b = "flicker", (p.flicker.low if idx % p.flicker.every == 0 else p.flicker.high)
        if s.blink is not None and s.mode != "out":
            s.b = s.blink
        props[p.name] = s

    for c in chars.values():  # gesture loops (e.g. scrubbing) ride on the current pose
        loop = bank.poses[c.pose_name].loop
        if c.loop and loop is not None:
            ph = sym.t_draw * 2 * math.pi * loop.hz
            attr = f"hand_{loop.hand}"
            x, y, z = getattr(c.pose, attr)
            c.pose = replace(c.pose, **{attr: (x + loop.radius[0] * math.cos(ph), y + loop.radius[1] * math.sin(ph), z)})

    preset = bank.cameras[sym.camera.preset]
    span, rel_move = sym.camera.span, sym.camera.since  # the preset's move runs from the cut to the shot's end
    ks = smooth(rel_move / span) if math.isfinite(span) and span > 0 else 0.0
    focal = lerp(preset.focal, preset.focal_to if preset.focal_to is not None else preset.focal, ks)
    az = lerp(preset.az, preset.az_to if preset.az_to is not None else preset.az, ks)
    if preset.punch is not None:
        pk = e_out(min(max((rel_move - preset.punch.at) / preset.punch.over, 0.0), 1.0))
        focal = lerp(focal, preset.punch.to, pk)
    cam = CamState(az, preset.el, preset.dist, tuple(preset.target), focal)
    graphics = [GraphicState(g.key, g.show, g.k) for g in sym.graphics]
    return FrameState(sym.shot, sym.set, sym.door, cam, chars, props, graphics, list(sym.fx))
