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
    return max(i for i, sh in enumerate(scene.shots) if float(sh.at) <= max(t, 0.0))


def _progress(b: Beat, rel: float) -> float | None:
    at = float(b.at)  # SentenceAnchor is resolved to a float before the timeline ever runs
    if rel < at:
        return None
    over = b.over or 0.0  # optional beat fields are None when not given: instant, smooth
    k = 1.0 if over <= 0 else min((rel - at) / over, 1.0)
    return EASES[b.ease or "smooth"](k)


# -- The symbolic timeline (E11): engine-neutral names and eased progress, no bank. Any engine
# folds it over its own spots, poses and cameras (the 2.5D state_at below; toy3d in JS). --

@dataclass(frozen=True)
class ActorAt:
    """Where the shot places an actor: every change starts from here."""
    name: str
    character: str
    spot: str
    pose: str
    expr: str
    layer: str | None
    loop: bool | None


@dataclass(frozen=True)
class Change:
    """A started move, pose or face beat with its eased progress `k` (0..1). Changes come in
    play order (by time, then as listed), and an engine folds them in that order: a face aims at
    the other actor's position as the changes before it left it."""
    verb: str                   # "move" | "pose" | "face"
    who: str
    to: str                     # the spot, the pose, or the actor faced
    expr: str | None = None     # pose: the expression it blends to
    k: float = 1.0
    bob: float | None = None    # move: the lift (toon2d)
    since: float = 0.0          # seconds since the beat started (accents, envelopes, walk cycles)
    over: float = 0.0           # the beat's over: (0: instant)


@dataclass(frozen=True)
class PropAt:
    name: str
    item: str                   # the bank prop the use names (its `kind:` in the scene)
    on: str | None
    held_by: str | None
    b: float
    count: int
    mode: str                   # "on" | "out"
    smoke: float                # seconds since it went out
    blink: float | None         # a blink's level, while it lasts
    flicker: Flicker | None
    since: float | None = None  # seconds since its latest started beat (None: none yet)


@dataclass(frozen=True)
class DoorAt:
    """The latest started door beat, for engines whose door moves on its own after it (a spring)."""
    value: float                # the folded openness, as `door`
    to: str                     # "open" | "close"
    since: float
    over: float


@dataclass(frozen=True)
class GraphicAt:
    key: str
    show: Show
    k: float                    # pop progress 0..1, linear: the engine shapes the pop


@dataclass(frozen=True)
class CameraAt:
    preset: str
    since: float                # seconds since the cut to this preset
    span: float                 # seconds from that cut to the shot's end (inf: open-ended)


@dataclass(frozen=True)
class SymbolicState:
    shot: int
    set: str
    t_draw: float               # drawing time, held at the shot's start
    door: float
    camera: CameraAt
    actors: tuple[ActorAt, ...]
    changes: tuple[Change, ...]
    props: tuple[PropAt, ...]
    graphics: tuple[GraphicAt, ...]
    fx: tuple
    door_at: DoorAt | None = None


def beats_at(scene: ToonScene, t: float, t_cam: float | None = None) -> SymbolicState:
    """What every actor, prop and graphic is doing at time `t`, as names and eased progress, for
    any engine. `t` is drawing time and `t_cam` camera time (default `t`), so an engine can draw
    on twos while its camera moves on ones. Pure: same inputs, same state."""
    t_cam = t if t_cam is None else t_cam
    i = shot_index(scene, t_cam)
    shot = scene.shots[i]
    start = float(shot.at)  # sentence anchors resolve to seconds before the timeline ever runs
    t_draw = max(t, start)
    rel, rel_cam = t_draw - start, t_cam - start
    actors = tuple(ActorAt(who, scene.cast[who], pl.spot, pl.pose, pl.expr, pl.layer, pl.loop)
                   for who, pl in shot.place.items())
    names = {a.name: (a.pose, a.expr) for a in actors}  # pose/expression once a blend completes
    work: dict[str, dict] = {
        name: {"item": pu.kind, "on": pu.on, "held_by": pu.held_by, "b": 1.0 if pu.b is None else pu.b,
               "count": pu.count or 0, "mode": "on", "smoke": 0.0, "blink": None, "since": None}
        for name, pu in shot.props.items()}
    flickers: dict[str, Flicker | None] = {}
    door = 0.0
    door_beat: tuple[str, float, float] | None = None  # (to, since, over) of the latest door beat
    changes: list[Change] = []
    graphics: dict[str, GraphicAt] = {}
    preset, cam_from = shot.camera, 0.0  # a camera beat cuts to its preset, whose move restarts

    for b in sorted(shot.beats, key=lambda x: x.at):
        if b.verb == "camera":  # the cut lands on camera time (ones), not drawing time (twos)
            if rel_cam >= float(b.at):
                preset, cam_from = b.camera, float(b.at)
            continue
        k = _progress(b, rel)
        if k is None:
            continue
        v, at = b.verb, float(b.at)
        since, over = rel - at, b.over or 0.0
        if v == "door":
            door = lerp(door, 1.0 if b.door == "open" else 0.0, k)
            door_beat = (b.door, since, over)
        elif v == "move":
            changes.append(Change("move", b.move, b.to, None, k, b.bob, since, over))
        elif v == "face":
            changes.append(Change("face", b.face, b.to, None, k, None, since, over))
        elif v == "pose":
            pose, expr = names[b.pose]
            to_pose, to_expr = b.to or pose, b.expr or expr
            changes.append(Change("pose", b.pose, to_pose, to_expr, k, None, since, over))
            if k >= 1.0:
                names[b.pose] = (to_pose, to_expr)
        elif v == "prop":
            s = work[b.prop]
            s["since"] = since
            if isinstance(b.to, dict):
                for key, val in b.to.items():
                    cur = s[key]
                    s[key] = int(cur + math.trunc((val - cur) * k)) if key == "count" else lerp(cur, val, k)
            if b.flicker is not None:
                flickers[b.prop] = b.flicker if isinstance(b.flicker, Flicker) else (Flicker() if b.flicker else None)
            if b.blink is not None and rel < at + b.blink.over:
                s["blink"] = b.blink.b
            if b.out:
                s["mode"], s["smoke"] = "out", rel - at
        elif v == "show":
            pop = POP if b.over is None else b.over  # over: 0 appears at once, no pop
            key = graphic_key(b.show)
            graphics[key] = GraphicAt(key, b.show, 1.0 if pop == 0 else min((rel - at) / pop, 1.0))
        elif v == "hide":
            graphics.pop(b.hide, None)

    props = tuple(PropAt(name, flicker=flickers.get(name), **s) for name, s in work.items())
    camera = CameraAt(preset, rel_cam - cam_from, shot_length(scene, i) - cam_from)
    door_at = DoorAt(door, *door_beat) if door_beat is not None else None
    return SymbolicState(i, shot.set, t_draw, door, camera, actors, tuple(changes), props,
                         tuple(graphics.values()), tuple(shot.fx), door_at)


def state_at(scene: ToonScene, bank: Bank, t_draw: float, t_cam: float | None = None) -> FrameState:
    """The 2.5D engine's frame: the symbolic timeline folded over this bank's spots, poses,
    props and cameras, with flicker on drawings (twos) and gesture loops."""
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
