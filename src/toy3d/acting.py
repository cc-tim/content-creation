"""toy3d acting (E11, plan rulings P2-R1…R6): one frame's spec from the symbolic timeline
(`toon.timeline.beats_at`) and the bank. Python does all the acting; the page only builds the world
from the bank and applies the spec.

The model, per actor, in play order:
- Poses fold into the rig's channels, `v = lerp(v, target, k)`. A full pose sets every body
  channel (unset = 0), a partial pose only its own. The cheated turns (`root.*`, `seat.*`, `look.*`:
  P2-R3) are not the body: a full pose leaves them where they are unless it names them, so Tim's
  chair turn survives his shock. Loops ride inside a pose's target, on scene time, and blend with
  it; `until_next: stop` ends a loop when the actor's next full pose starts.
- A move translates the actor (never turns it: P2-R5); a character with a `walk` also walks. The
  walk's terms enter the fold where the move does, so later poses blend them away.
- Accents add after the fold, timed from their pose's start; flags turn on once their pose is 5% in
  and stay on. A pose beat that names a pose blends it in from wherever the fold is (unless it's
  the pose already heading in); one without `to` only changes the face. A beat that names an
  expression switches the face as it starts; one that doesn't leaves the face alone.
- `face` aims at its target's root where that is at `t` (the snapshot's `aim(lion.root.position)`),
  turning the short way round.
  GuoGuo's look is that aim plus his `look.dy`, split between his body and head when seated.
- Engine programs (the walk, GuoGuo, the door, the bulb, the bubble, the laptop, the camera) are
  the snapshot's code with their constants in the bank.

The spec (JSON-able), world space, angles in radians:
  t, frame, set
  camera   {pos, target, fov, up}
  door     {angle, dust: None | {k, move, grow, alpha}}
  laptop   {spot, lines, cursor}
  actors   {name: {character, build, root {pos, yaw}, seat: None | {spot, pos, yaw}, joints, signals,
                   face, flags, sweat: None | {scale, y}, guo: None | {head_yaw, body_scale, body_py,
                   body_rz, flippers, eye, pupil, push, flipper_push}}}
  props    {name: {kind, on, anchor, level, lit, bob, tilt, glow, rays, smoke: [{k, dx, rise, grow, alpha}]}}
  bubbles  [{speaker, icons, right, up, bob, pop, bang}]
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from toon.beats import EASES, ActorAt, Change, PropAt, SymbolicState, beats_at, e_back, e_out, lerp
from toon.scene import ToonScene
from toy3d.bank import (
    Accent,
    Bump,
    CameraPreset,
    Character,
    DecaySine,
    Flap,
    GuoActing,
    HalfSine,
    Hold,
    Loop,
    Osc,
    Pose,
    PropDef,
    SetDef,
    Toy3DBank,
    Track,
    Walk,
)

FLAP_RAMP, FLAP_TAIL = 0.06, 0.25     # a flap eases in over 0.06 s and out over its last 0.25 s
FLAG_K = 0.05                         # a flag turns on once its pose is this far in
TURNS = ("root.", "seat.", "look.")    # cheated turns (P2-R3): a full pose's reset leaves them be
VEL_DT = 1 / 120                      # GuoGuo's hop speed: a backward difference over this step


def _seg(x: float, a: float, b: float) -> float:
    return min(1.0, max(0.0, (x - a) / (b - a)))


def _wave(kind: str, x: float) -> float:
    s = math.sin(x)
    return abs(s) if kind == "abs_sin" else s


def loop_value(loop: Loop, t: float) -> float:
    return loop.amp * _wave(loop.wave, loop.rate * t + loop.phase)


def accent_values(acc: Accent, since: float, t: float, stop: float | None = None) -> dict[str, float]:
    """One accent's additive values `since` seconds after its pose started, at scene time `t` (osc
    waves). `stop`: when the actor's next full pose starts, in the same since (`until_next`)."""
    if isinstance(acc, HalfSine):
        return {acc.channel: acc.amp * math.sin(math.pi * _seg(since, *acc.span))}
    if isinstance(acc, Bump):
        g = sum(math.exp(-math.pow((since - c) / acc.width, 2)) for c in acc.at)
        return {ch: amp * g for ch, amp in acc.channels.items()}
    if isinstance(acc, DecaySine):
        u = since - acc.start
        return {acc.channel: acc.amp * math.exp(-u * acc.decay) * math.sin(u * acc.freq) if u > 0 else 0.0}
    if isinstance(acc, Flap):
        return {acc.channel: acc.amp * math.sin((since - acc.start) * math.pi * 2 * acc.hz)
                * _seg(since, acc.start, acc.start + FLAP_RAMP) * (1 - _seg(since, acc.end - FLAP_TAIL, acc.end))}
    on = acc.after is None or since > acc.after
    env = 1 - _seg(since, *acc.fade) if acc.fade is not None else 1.0
    if isinstance(acc, Hold):
        return {acc.channel: acc.amp * env if on else 0.0}
    assert isinstance(acc, Osc)
    if acc.until_next is not None and stop is not None:
        env *= 1 - _seg(since, stop, stop + acc.until_next.fade) if acc.until_next.fade > 0 else float(since < stop)
    return {acc.channel: acc.amp * _wave(acc.wave, acc.rate * t + acc.phase) * env if on else 0.0}


@dataclass(frozen=True)
class _Taken:
    """A pose an actor took: its placement (order -1) or a started pose change."""
    name: str
    pose: Pose
    since: float
    k: float
    order: int


@dataclass(frozen=True)
class _Walked:
    change: Change
    p0: tuple[float, ...]
    p1: tuple[float, ...]
    order: int


def _lerp3(a, b, k: float) -> list[float]:
    return [lerp(a[i], b[i], k) for i in range(3)]


def _positions(sym: SymbolicState, setdef: SetDef) -> tuple[dict[str, list[float]], dict[str, list[_Walked]]]:
    """Every actor's root at `t`, folding moves in play order, and the moves each one made."""
    pos = {a.name: list(setdef.spots[a.spot].pos) for a in sym.actors}
    moves: dict[str, list[_Walked]] = {}
    for i, c in enumerate(sym.changes):
        if c.verb == "move":
            p0, p1 = tuple(pos[c.who]), tuple(setdef.spots[c.to].pos)
            pos[c.who] = _lerp3(p0, p1, c.k)
            moves.setdefault(c.who, []).append(_Walked(c, p0, p1, i))
    return pos, moves


def _facing(sym: SymbolicState, setdef: SetDef, pos: dict[str, list[float]]) -> dict[str, float]:
    yaw = {a.name: math.radians(setdef.spots[a.spot].yaw) for a in sym.actors}
    for c in sym.changes:
        if c.verb == "face":
            me, to = pos[c.who], pos[c.to]
            turn = (math.atan2(to[0] - me[0], to[2] - me[2]) - yaw[c.who] + math.pi) % (2 * math.pi) - math.pi
            yaw[c.who] = yaw[c.who] + turn * c.k    # the short way round
    return yaw


def _walk(w: Walk, scale: float, m: _Walked) -> dict[str, float]:
    """The lioness's walk (scene.js poseLion): phase from the distance walked, in her own scale; a
    step envelope that settles over 1/settle s after she arrives."""
    c = m.change
    wk = 1.0 if c.over <= 0 else min(1.0, max(0.0, c.since / c.over))
    ph = c.k * math.dist(m.p0, m.p1) / scale / w.stride * math.pi
    step = 1.0 if 0 < wk < 1 else max(0.0, 1 - (c.since - c.over) * w.settle) if wk >= 1 else 0.0
    s = math.sin(ph)
    return {"hips.py": w.bob * abs(s) * step, "body.rz": w.sway * s * step,
            "leg_l.j1.rx": -w.hip_swing * s * step, "leg_r.j1.rx": w.hip_swing * s * step,
            "leg_l.j2.rx": w.knee * max(0.0, math.sin(ph + math.pi)) * step, "leg_r.j2.rx": w.knee * max(0.0, s) * step,
            "arm_l.j1.rx": w.arm_swing * s * step, "arm_r.j1.rx": -w.arm_swing * s * step}


@dataclass
class _Acted:
    channels: dict[str, float]
    taken: list[_Taken]
    flags: set[str]
    expr: str
    expr_since: float
    hop_before: float           # GuoGuo's hop channel VEL_DT earlier (his hop speed)


def _next_full(taken: list[_Taken], i: int) -> _Taken | None:
    return next((e for e in taken[i + 1:] if not e.pose.partial), None)


def _act(actor: ActorAt, ch: Character, poses: dict[str, Pose], sym: SymbolicState, walks: list[_Walked],
         rel: float, t: float) -> _Acted:
    taken = [_Taken(actor.pose, poses[actor.pose], rel, 1.0, -1)]
    shown, shown_since = actor.expr, rel         # the face on screen: switches when a beat starts
    for i, c in enumerate(sym.changes):
        if c.verb != "pose" or c.who != actor.name:
            continue
        if c.expr_set and c.expr != shown:   # an authored expression switches the face as its beat starts
            shown, shown_since = c.expr, c.since
        # An authored pose blends in from wherever the fold is, unless it's the one already heading
        # in; a beat without `to` only changes the face.
        if c.to_set and c.to != taken[-1].name:
            taken.append(_Taken(c.to, poses[c.to], c.since, c.k, i))
    events: list[tuple[int, _Taken | _Walked]] = [(e.order, e) for e in taken]
    if ch.walk is not None:
        events += [(m.order, m) for m in walks]
    v = dict.fromkeys(ch.rig.channels, 0.0)
    loops_on = actor.loop is not False
    for _, ev in sorted(events, key=lambda x: x[0]):
        if isinstance(ev, _Walked):
            assert ch.walk is not None
            for name, d in _walk(ch.walk, ch.scale, ev).items():
                v[name] += d
            continue
        p = ev.pose
        target = {} if p.partial else {name: 0.0 for name in v if not name.startswith(TURNS)}
        target.update(p.channels)
        if loops_on:
            stopped = _next_full(taken, taken.index(ev)) is not None
            for lp in p.loops:
                if not (lp.until_next == "stop" and stopped):
                    target[lp.channel] = target.get(lp.channel, 0.0) + loop_value(lp, t)
        for name, x in target.items():
            v[name] = lerp(v[name], x, ev.k)
    flags: set[str] = set()
    hop_before = v.get("hop", 0.0)
    for i, e in enumerate(taken):
        nxt = _next_full(taken, i)
        stop = e.since - nxt.since if nxt is not None else None
        for acc in e.pose.accents:
            for name, d in accent_values(acc, e.since, t, stop).items():
                v[name] += d
            if "hop" in ch.rig.channels:
                hop_before += accent_values(acc, e.since - VEL_DT, t - VEL_DT, stop).get("hop", 0.0)
        flags |= {f.name for f in e.pose.flags if e.k > FLAG_K and e.since >= f.from_}
    return _Acted(v, taken, flags, shown, shown_since, hop_before)


def _guo(g: GuoActing, cls: str, a: _Acted, look: float, t: float) -> tuple[float, dict[str, Any]]:
    """GuoGuo's rig from his acting signals (scene.js poseGuo): the root yaw and his `guo` spec."""
    v = a.channels
    hop_k = g.hop_scale[cls]
    vel = hop_k * (v["hop"] - a.hop_before) / VEL_DT
    sq = g.squash
    sy = 1 + sq.sq * v["sq"] + sq.speed * min(1.0, abs(vel) / sq.speed_full) + sq.land * v["land"] + sq.wob * v["wob"]
    if cls == "sit":   # a seated plush stays put; the head does most of the turning
        body = g.look.seat_yaw + g.look.body_share * (look - g.look.seat_yaw)
        head = max(-g.look.head_clamp, min(g.look.head_clamp, look - body))
    else:
        body, head = look, 0.0
    fl = g.flippers
    fz = v["fidle"] + fl.flap * v["flap"] + fl.jig * v["jig"] + fl.raise_ * v["raise"]
    fp = g.fur_push
    push = fp.base + fp.speed * vel + fp.land * v["land"] + fp.wob * v["wob"]
    flipper_push = push
    flaps = [(e.since - acc.start, acc.hz) for e in a.taken for acc in e.pose.accents
             if isinstance(acc, Flap) and e.since >= acc.start]
    if flaps and abs(v["flap"]) > fp.whip_threshold:
        since, hz = max(flaps)                   # the earliest flap's phase (scene.js: t - t0)
        flipper_push = push + fp.whip * math.cos(since * math.pi * 2 * hz)
    wide = "wide_eyes" in a.flags
    return body, {"head_yaw": head, "body_scale": [1 / math.sqrt(sy), sy, 1 / math.sqrt(sy)],
                  "body_py": hop_k * v["hop"] + v["bob"], "body_rz": v["body.rz"], "flippers": [-fz, fz],
                  "eye": g.wide_eyes.eye if wide else 1.0, "pupil": g.wide_eyes.pupil if wide else 1.0,
                  "push": push, "flipper_push": flipper_push}


def _typed(a: _Acted, rel: float) -> float:
    """Seconds the actor has held a pose flagged `typing` (until a full pose replaces it)."""
    total = 0.0
    full = [e for e in a.taken if not e.pose.partial]
    for i, e in enumerate(full):
        if any(f.name == "typing" for f in e.pose.flags):
            start = rel - e.since
            end = rel - full[i + 1].since if i + 1 < len(full) else rel
            total += max(0.0, min(end, rel) - start)
    return total


def _track(tr: Track, lt: float) -> Any:
    v = tr.start
    for tw in tr.tweens:
        if lt < tw.at:
            continue
        k = 1.0 if tw.over <= 0 else EASES[tw.ease](min(1.0, (lt - tw.at) / tw.over))
        v = lerp(v, tw.to, k) if isinstance(v, float) else _lerp3(v, tw.to, k)
    return v if isinstance(v, float) else list(v)


def _camera(cam: CameraPreset, lt: float) -> dict[str, Any]:
    if cam.orbit is not None:
        piv, az, el, d = (_track(x, lt) for x in (cam.orbit.pivot, cam.orbit.az, cam.orbit.el, cam.orbit.dist))
        az, el = math.radians(az), math.radians(el)
        pos = [piv[0] + d * math.cos(el) * math.sin(az), piv[1] + d * math.sin(el),
               piv[2] + d * math.cos(el) * math.cos(az)]
    else:
        assert cam.pos is not None
        pos = list(cam.pos)
    return {"pos": pos, "target": _track(cam.target, lt), "fov": _track(cam.fov, lt), "up": list(cam.up)}


def _door(sym: SymbolicState, setdef: SetDef, opened: float | None) -> dict[str, Any]:
    d, da = setdef.door, sym.door_at
    if da is None:
        return {"angle": 0.0, "dust": None}
    if da.to == "close":
        angle = d.rest * sym.door
    elif da.since <= da.over:
        angle = d.open * sym.door
    else:
        u = da.since - da.over
        angle = d.rest + (d.open - d.rest) * math.exp(-u * d.decay) * math.cos(u * d.freq)
    dust = None
    if opened is not None:
        k = _seg(opened, *d.dust.span)
        dust = {"k": k, "move": e_out(k), "grow": d.dust.grow[0] + d.dust.grow[1] * e_out(k),
                "alpha": d.dust.alpha * (1 - k)}
    return {"angle": angle, "dust": dust}


def _bulb(p: PropAt, pd: PropDef, t: float, frame: int) -> dict[str, Any]:
    # The fold's lerp(cur, b, 1) can miss an authored b by a bit, and the lit / rays thresholds
    # compare with `>`: the snapshot's 0.05 must stay unlit.
    level = round(p.b, 12)
    if p.mode != "out":
        if p.flicker is not None:
            level = p.flicker.low if frame % p.flicker.every == 0 else p.flicker.high
        if p.blink is not None:
            level = p.blink
    out = pd.out
    gone = p.mode == "out"
    dead = e_out(_seg(p.smoke, 0.0, out.over)) if gone else 0.0
    smoke = []
    for i in range(out.smoke):
        k = _seg(p.smoke, out.stagger * i, out.smoke_span + out.stagger * i) if gone else 0.0
        smoke.append({"k": k, "dx": out.sway.amp * math.sin(i * out.sway.phase_step + t * out.sway.rate),
                      "rise": out.rise[0] + out.rise[1] * k, "grow": out.grow[0] + out.grow[1] * k,
                      "alpha": out.alpha * (1 - k)})
    return {"kind": pd.kind, "on": p.on, "anchor": list(pd.anchor), "level": level, "lit": level > pd.lit_min,
            "bob": pd.drift.bob * math.sin(t * pd.drift.bob_rate) - out.droop * dead,
            "tilt": pd.drift.tilt * math.sin(t * pd.drift.tilt_rate) + out.tilt * dead,
            "glow": pd.glow.base + pd.glow.amp * math.sin(t * pd.glow.rate),
            "rays": 1 + pd.rays.amp * math.sin(t * pd.rays.rate) if level > pd.rays.min_level else 0,
            "smoke": smoke}


def _latest_open(scene: ToonScene, shot_index: int, rel: float) -> float | None:
    """Seconds since the shot's latest started door open (its dust outlives a later close)."""
    opens = [float(b.at) for b in scene.shots[shot_index].beats if b.verb == "door" and b.door == "open"
             and float(b.at) <= rel]
    return rel - max(opens) if opens else None


def _split(kind: str, v: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """Rig channels → joints (`node.prop`, applied to the rig's nodes) and signals (the rest)."""
    if kind == "guoguo":
        return {}, dict(v)
    joints = {k: x for k, x in v.items() if "." in k and not k.startswith(("root.", "seat."))}
    return joints, {k: x for k, x in v.items() if "." not in k}


def resolve(scene: ToonScene, bank: Toy3DBank, t: float) -> dict[str, Any]:
    """The frame spec at time `t` (pure: same inputs, same spec)."""
    sym = beats_at(scene, t)
    start = float(scene.shots[sym.shot].at)
    tt = sym.t_draw                              # scene time: loops, waves, drift
    rel = tt - start                             # shot time: beats
    fps = bank.style.fps
    frame = math.floor(tt * fps + 1e-9)
    setdef = bank.sets[sym.set]
    pos, moves = _positions(sym, setdef)
    facing = _facing(sym, setdef, pos)

    actors: dict[str, Any] = {}
    acted: dict[str, _Acted] = {}
    for a in sym.actors:
        ch = bank.characters[a.character]
        acts = _act(a, ch, bank.poses[a.character], sym, moves.get(a.name, []), rel, tt)
        acted[a.name] = acts
        full = [e for e in acts.taken if not e.pose.partial]
        cls = full[-1].pose.class_ if full else acts.taken[0].pose.class_
        v = acts.channels
        root_pos, yaw, seat, guo = list(pos[a.name]), facing[a.name], None, None
        spot = setdef.spots[a.spot]
        if ch.rig.kind == "guoguo":
            assert ch.guoguo is not None
            yaw, guo = _guo(ch.guoguo, cls, acts, facing[a.name] + v["look.dy"], tt)
            build = f"guoguo_{'seated' if cls == 'sit' else 'standing'}"
        else:
            build = ch.rig.kind
            yaw += v.get("root.ry", 0.0)
            if spot.seat is not None and ch.seat_height is not None and a.name not in moves:
                sp = list(spot.pos)
                sp[2] += v.get("seat.pz", 0.0)
                seat = {"spot": a.spot, "pos": sp, "yaw": math.radians(spot.yaw) + v.get("seat.ry", 0.0)}
                root_pos = [sp[0], sp[1] + ch.seat_height, sp[2]]
                yaw += v.get("seat.ry", 0.0)
        joints, signals = _split(ch.rig.kind, v)
        expression = bank.expressions[a.character][acts.expr]
        sweat = None
        if expression.sweat is not None:
            sw = expression.sweat
            dk = _seg(acts.expr_since, *sw.appear)
            if dk > 0:
                sweat = {"scale": max(0.001, e_back(dk)), "y": sw.y0 + sw.dy * e_out(_seg(acts.expr_since, *sw.fall))}
        actors[a.name] = {"character": a.character, "build": build, "root": {"pos": root_pos, "yaw": yaw},
                          "seat": seat, "joints": joints, "signals": signals, "face": expression.decal,
                          "flags": sorted(acts.flags), "sweat": sweat, "guo": guo}

    laptop = setdef.laptop
    typist = next((a.name for a in sym.actors if a.spot == laptop.spot), None)
    typed = _typed(acted[typist], rel) if typist is not None else 0.0
    bubbles = []
    for g in sym.graphics:
        if g.show.bubble is None or not g.k > 0:
            continue
        speaker = g.show.from_
        assert speaker is not None
        bb = bank.bubble
        bang = actors[speaker]["signals"].get(bb.bang.signal, 0.0) if speaker in actors else 0.0
        bubbles.append({"speaker": speaker, "icons": list(g.show.bubble), "right": bb.offset.right,
                        "up": bb.offset.up, "bob": bb.bob.amp * math.sin(tt * bb.bob.rate),
                        "pop": max(0.001, e_back(g.k)) * bb.pop.scale, "bang": 1 + bang})
    return {
        "t": t, "frame": round(t * fps), "set": sym.set,
        "camera": _camera(bank.cameras[sym.camera.preset], sym.camera.since),
        "door": _door(sym, setdef, _latest_open(scene, sym.shot, rel)),
        "laptop": {"spot": laptop.spot, "lines": min(laptop.lines + math.floor(typed * laptop.rate), laptop.max_lines),
                   "cursor": math.floor(tt * laptop.cursor_rate) % 2 == 0},
        "actors": actors,
        "props": {p.name: _bulb(p, bank.props[p.item], tt, frame) for p in sym.props},
        "bubbles": bubbles,
    }
