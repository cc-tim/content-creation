"""The symbolic timeline (E11): what every actor, prop, graphic and the camera are doing at time t,
as names and eased progress, for any engine. Engine-neutral: it reads the scene contract
(toon.scene) and nothing of either engine's bank, kit or drawing stack. Pure: same inputs, same
state. The 2.5D engine folds it in toon.timeline.state_at; toy3d in toy3d.acting.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from toon.scene import Beat, Flicker, Show, ToonScene, graphic_key, shot_length

POP = 0.25   # a show beat's default pop, in seconds


def lerp(a, b, k):
    return a + (b - a) * k


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def e_out(x):
    return 1 - (1 - x) ** 3


def e_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def e_lin(x):
    return x


def e_inout(x):
    """Cubic in-out: the toy3d tryout's `ease` (r7-3d scene.js), the camera's and the turns'."""
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


EASES = {"linear": e_lin, "smooth": smooth, "out": e_out, "back": e_back, "inout": e_inout}


def shot_index(scene: ToonScene, t: float) -> int:
    return max(i for i, sh in enumerate(scene.shots) if float(sh.at) <= max(t, 0.0))


def _progress(b: Beat, rel: float) -> float | None:
    at = float(b.at)  # SentenceAnchor is resolved to a float before the timeline ever runs
    if rel < at:
        return None
    over = b.over or 0.0  # optional beat fields are None when not given: instant, smooth
    k = 1.0 if over <= 0 else min((rel - at) / over, 1.0)
    return EASES[b.ease or "smooth"](k)


# -- The symbolic timeline: engine-neutral names and eased progress, no bank. Each engine folds it
# over its own spots, poses and cameras (toon.timeline.state_at; toy3d.acting.resolve). --

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
    expr_set: bool = False      # pose: the beat names its expression (else `expr` is inherited)
    to_set: bool = False        # pose: the beat names its pose (else `to` is the current one)


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
            changes.append(Change("pose", b.pose, to_pose, to_expr, k, None, since, over, b.expr is not None,
                                  b.to is not None))
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
