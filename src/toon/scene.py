"""Scene files: shots of bank items + timed beats. Wordless by construction (icon names only)."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from toon.bank import Bank, default_root
from toon.kit.icons import ICONS

Ease = Literal["linear", "smooth", "out", "back"]
VERBS = ("door", "move", "pose", "face", "prop", "show", "hide", "camera")
SHOW_KINDS = ("speed_lines", "bubble", "anger", "x_card", "check_pill")
PROP_USE_FIELDS = ("on", "held_by", "b", "count")
# Per bank-prop kind: (use fields it needs, use fields it draws, states a `to:` beat animates).
# Anything else would load cleanly and be silently ignored by the renderer, so it is rejected.
PROP_KINDS: dict[str, tuple[frozenset[str], frozenset[str], frozenset[str]]] = {
    "idea_bulb": (frozenset({"on"}), frozenset({"on", "b"}), frozenset({"b"})),
    "plate": (frozenset({"held_by"}), frozenset({"held_by"}), frozenset()),
    "plate_stack": (frozenset({"count"}), frozenset({"count"}), frozenset({"count"})),
}


class _SceneLoader(yaml.SafeLoader):
    """A YAML loader for scene files that keeps `on`/`off`/`yes`/`no` as plain strings.

    ``PropUse.on`` (e.g. ``idea: {kind: idea_bulb, on: tim}``) collides with YAML 1.1's
    implicit booleans (``on|On|ON|off|Off|OFF|yes|Yes|YES|no|No|NO``), which `yaml.safe_load`
    would otherwise turn into `True`/`False` mapping keys — see the design doc's own example
    at `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md` line 118. `true`/`false`
    (used by e.g. `Place.loop`) are left resolving to booleans as normal.
    """


_SceneLoader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if not (tag == "tag:yaml.org,2002:bool" and ch in "yYnNoO")]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class SceneError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SentenceAnchor(_Strict):
    sentence: int = Field(ge=1)


class Place(_Strict):
    spot: str
    pose: str
    expr: str = "neutral"
    layer: Literal["split", "low"] = "split"   # low: whole character sits behind the set's mid layer
    loop: bool = True


class PropUse(_Strict):
    kind: str
    on: str | None = None
    held_by: str | None = None
    b: float | None = None
    count: int | None = None


class Glow(_Strict):
    at: tuple[float, float, float]
    radius: float
    color: Literal["warm", "cool"]
    alpha: float


class Fx(_Strict):
    glow: Glow


class Show(_Strict):
    speed_lines: str | None = None
    bubble: Annotated[list[str], Field(min_length=1)] | None = None
    from_: str | None = Field(default=None, alias="from")
    anger: str | None = None
    x_card: str | None = None
    check_pill: str | None = None
    at: tuple[float, float] | None = None   # screen fractions, for cards

    @model_validator(mode="after")
    def _one_kind(self):
        kinds = [k for k in SHOW_KINDS if getattr(self, k) is not None]
        if len(kinds) != 1:
            raise ValueError(f"show needs exactly one of {SHOW_KINDS}, got {kinds or 'none'}")
        if self.bubble is not None and self.from_ is None:
            raise ValueError("bubble needs from: <cast name>")
        if (self.x_card or self.check_pill) and self.at is None:
            raise ValueError("cards need at: [x, y] (screen fractions)")
        return self

    @property
    def kind(self) -> str:
        return next(k for k in SHOW_KINDS if getattr(self, k) is not None)


class Flicker(_Strict):
    every: int = 4
    low: float = 0.35
    high: float = 0.85


class Blink(_Strict):
    b: float
    over: float


class Beat(_Strict):
    at: float | SentenceAnchor
    over: float = 0.0
    ease: Ease = "smooth"
    door: Literal["open", "close"] | None = None
    move: str | None = None
    pose: str | None = None
    face: str | None = None
    prop: str | None = None
    show: Show | None = None
    hide: str | None = None       # a graphic key, e.g. "bubble:lioness"
    camera: str | None = None
    to: str | dict[str, float] | None = None
    expr: str | None = None
    bob: float = 0.0
    flicker: Flicker | bool | None = None
    blink: Blink | None = None
    out: bool | None = None

    @model_validator(mode="after")
    def _one_verb(self):
        verbs = [v for v in VERBS if getattr(self, v) is not None]
        if len(verbs) != 1:
            raise ValueError(f"a beat needs exactly one verb of {VERBS}, got {verbs or 'none'}")
        return self

    @property
    def verb(self) -> str:
        return next(v for v in VERBS if getattr(self, v) is not None)


class Shot(_Strict):
    at: float
    set: str
    camera: str
    place: dict[str, Place]
    props: dict[str, PropUse] = {}
    fx: list[Fx] = []
    beats: list[Beat] = []


class ToonScene(_Strict):
    id: str
    duration: float | None = None
    cast: dict[str, str]
    shots: list[Shot] = Field(min_length=1)
    boil: Literal["full", "soft", "still"] | None = None  # overrides the bank style's default


def graphic_key(show: Show) -> str:
    """`<kind>:<target>` — the name a `hide:` beat uses. Keyed on the show's own kind, so a
    stray field of another kind can never pick the target."""
    target = {"speed_lines": show.speed_lines, "bubble": show.from_, "anger": show.anger,
              "x_card": show.x_card, "check_pill": show.check_pill}[show.kind]
    return f"{show.kind}:{target}"


def shot_length(scene: ToonScene, i: int) -> float:
    if i + 1 < len(scene.shots):
        return scene.shots[i + 1].at - scene.shots[i].at
    return scene.duration - scene.shots[i].at if scene.duration is not None else math.inf


_SENTENCE = re.compile(r"(?<=[.!?。！？…])\s*")


def sentence_starts(narration: str, duration: float) -> list[float]:
    parts = [s for s in _SENTENCE.split(narration.strip()) if s.strip()]
    total = sum(len(s) for s in parts) or 1
    starts, acc = [], 0
    for s in parts:
        starts.append(duration * acc / total)
        acc += len(s)
    return starts


def _resolve_anchors(scene: ToonScene, narration: str | None) -> ToonScene:
    anchored = [(i, j) for i, sh in enumerate(scene.shots) for j, b in enumerate(sh.beats)
                if isinstance(b.at, SentenceAnchor)]
    if not anchored:
        return scene
    if not narration or scene.duration is None:
        raise SceneError([f"shots[{i}].beats[{j}].at: sentence anchors need the scene's narration and duration"
                          for i, j in anchored])
    starts = sentence_starts(narration, scene.duration)
    problems, shots = [], []
    for i, sh in enumerate(scene.shots):
        beats = []
        for j, b in enumerate(sh.beats):
            if isinstance(b.at, SentenceAnchor):
                n = b.at.sentence
                if n > len(starts):
                    problems.append(f"shots[{i}].beats[{j}].at: sentence {n}, but narration has {len(starts)}")
                else:
                    b = b.model_copy(update={"at": starts[n - 1] - sh.at})
            beats.append(b)
        shots.append(sh.model_copy(update={"beats": beats}))
    if problems:
        raise SceneError(problems)
    return scene.model_copy(update={"shots": shots})


def _check(scene: ToonScene, bank: Bank) -> list[str]:
    p: list[str] = []
    for who, char in scene.cast.items():
        if char not in bank.characters:
            p.append(f"cast.{who}: unknown character {char!r} (bank has {sorted(bank.characters)})")
    last = -1.0
    for i, shot in enumerate(scene.shots):
        w = f"shots[{i}]"
        if i == 0 and shot.at != 0:
            p.append(f"{w}.at: the first shot must start at 0")
        if shot.at <= last:
            p.append(f"{w}.at: shots must start in increasing order")
        last = shot.at
        set_def = bank.sets.get(shot.set)
        spots = set_def.spots if set_def else {}
        if set_def is None:
            p.append(f"{w}.set: unknown set {shot.set!r} (bank has {sorted(bank.sets)})")
        if shot.camera not in bank.cameras:
            p.append(f"{w}.camera: unknown camera {shot.camera!r} (bank has {sorted(bank.cameras)})")
        for who, pl in shot.place.items():
            pw = f"{w}.place.{who}"
            if who not in scene.cast:
                p.append(f"{pw}: not in cast")
            if set_def is not None and pl.spot not in spots:
                p.append(f"{pw}.spot: unknown spot {pl.spot!r} in set {shot.set!r}")
            if pl.pose not in bank.poses:
                p.append(f"{pw}.pose: unknown pose {pl.pose!r}")
            if pl.expr not in bank.expressions:
                p.append(f"{pw}.expr: unknown expression {pl.expr!r}")
        for name, pu in shot.props.items():
            uw = f"{w}.props.{name}"
            if pu.kind not in bank.props:
                p.append(f"{uw}.kind: unknown prop {pu.kind!r}")
            else:
                p += _check_prop_use(pu, uw, bank.props[pu.kind].kind)
            for field, ref in (("on", pu.on), ("held_by", pu.held_by)):
                if ref is not None and ref not in shot.place:
                    p.append(f"{uw}.{field}: {ref!r} is not placed in this shot")
        length = shot_length(scene, i)
        # Collect shown graphics in this shot
        shown: dict[str, float] = {}  # graphic_key -> at time
        for _j, b in enumerate(shot.beats):
            if b.verb == "show" and isinstance(b.at, float):
                shown[graphic_key(b.show)] = b.at
        for j, b in enumerate(shot.beats):
            bw = f"{w}.beats[{j}]"
            if isinstance(b.at, (int, float)) and not (0 <= b.at <= length):
                p.append(f"{bw}.at: {b.at:g}s is outside the shot (0–{length:g}s)")
            p += _check_beat(b, bw, shot, spots, bank, shown)
    return p


def _a(kind: str) -> str:
    return f"an {kind}" if kind[0] in "aeiou" else f"a {kind}"


def _check_prop_use(pu: PropUse, uw: str, kind: str) -> list[str]:
    need, draws, _ = PROP_KINDS[kind]
    p: list[str] = []
    for field in PROP_USE_FIELDS:
        value = getattr(pu, field)
        if value is None and field in need:
            p.append(f"{uw}.{field}: {_a(kind)} prop needs {field}:")
        elif value is not None and field not in draws:
            p.append(f"{uw}.{field}: not valid on {_a(kind)} prop (it takes {sorted(draws)})")
    return p


def _check_beat(b: Beat, bw: str, shot: Shot, spots: dict, bank: Bank,
                 shown: dict[str, float] | None = None) -> list[str]:
    p: list[str] = []
    placed = shot.place
    v = b.verb
    if v in ("door", "show", "hide", "camera") and b.to is not None:
        p.append(f"{bw}.to: not valid with a {v} beat")
    if v == "move":
        if b.move not in placed:
            p.append(f"{bw}.move: {b.move!r} is not placed in this shot")
        if not isinstance(b.to, str) or b.to not in spots:
            p.append(f"{bw}.to: unknown spot {b.to!r}")
    elif v == "pose":
        if b.pose not in placed:
            p.append(f"{bw}.pose: {b.pose!r} is not placed in this shot")
        elif b.to is not None:
            if not isinstance(b.to, str) or b.to not in bank.poses:
                p.append(f"{bw}.to: unknown pose {b.to!r}")
            elif bank.poses[b.to].hip != bank.poses[placed[b.pose].pose].hip:
                p.append(f"{bw}.to: pose {b.to!r} changes hip ({bank.poses[placed[b.pose].pose].hip} → "
                         f"{bank.poses[b.to].hip}); cut to a new shot instead")
        if b.expr is not None and b.expr not in bank.expressions:
            p.append(f"{bw}.expr: unknown expression {b.expr!r}")
        if b.to is None and b.expr is None:
            p.append(f"{bw}: a pose beat needs to: <pose> and/or expr: <expression>")
    elif v == "face":
        if b.face not in placed or not isinstance(b.to, str) or b.to not in placed:
            p.append(f"{bw}: face needs two characters placed in this shot")
    elif v == "prop":
        pu = shot.props.get(b.prop)
        if pu is None:
            p.append(f"{bw}.prop: unknown prop use {b.prop!r} in this shot")
        if isinstance(b.to, str):
            p.append(f"{bw}.to: prop beats take a mapping like {{b: 0.3}}")
        elif isinstance(b.to, dict) and pu is not None and pu.kind in bank.props:
            kind = bank.props[pu.kind].kind
            states = PROP_KINDS[kind][2]
            for key in b.to:
                if key not in states:
                    p.append(f"{bw}.to.{key}: {_a(kind)} prop has no {key!r} state "
                             f"(it animates {sorted(states) or 'nothing'})")
        if not (isinstance(b.to, dict) or b.flicker is not None or b.blink or b.out):
            p.append(f"{bw}: a prop beat needs to / flicker / blink / out")
    elif v == "show":
        s = b.show
        for ref in (s.speed_lines, s.from_, s.anger):
            if ref is not None and ref not in placed:
                p.append(f"{bw}.show: {ref!r} is not placed in this shot")
        if s.from_ is not None and s.kind != "bubble":
            p.append(f"{bw}.show.from: only valid with a bubble show")
        if s.at is not None and s.kind not in ("x_card", "check_pill"):
            p.append(f"{bw}.show.at: only valid with an x_card or check_pill show")
        for icon in (s.bubble or []) + [x for x in (s.x_card, s.check_pill) if x]:
            if icon not in ICONS:
                p.append(f"{bw}.show: {icon!r} is not an icon — animation is wordless; "
                         f"use one of {sorted(ICONS)}")
    elif v == "hide":
        if shown is None or b.hide not in shown:
            keys = sorted(shown.keys()) if shown else []
            p.append(f"{bw}.hide: {b.hide!r} does not match a graphic shown earlier in this shot (shown: {keys})")
        elif isinstance(b.at, float) and shown[b.hide] > b.at:
            p.append(f"{bw}.hide: {b.hide!r} was shown at {shown[b.hide]:g}s, after this hide at {b.at:g}s")
    elif v == "camera" and b.camera not in bank.cameras:
        p.append(f"{bw}.camera: unknown camera {b.camera!r}")
    # Check verb-specific fields on other verbs
    if v != "pose" and b.expr is not None:
        p.append(f"{bw}.expr: only valid with a pose beat")
    if v != "prop" and b.flicker is not None:
        p.append(f"{bw}.flicker: only valid with a prop beat")
    if v != "prop" and b.blink is not None:
        p.append(f"{bw}.blink: only valid with a prop beat")
    if v != "prop" and b.out:
        p.append(f"{bw}.out: only valid with a prop beat")
    if v != "move" and b.bob != 0.0:
        p.append(f"{bw}.bob: only valid with a move beat")
    return p


def load_scene(data: dict, bank: Bank, narration: str | None = None,
               duration: float | None = None) -> ToonScene:
    try:
        scene = ToonScene.model_validate(data)
    except ValidationError as exc:
        raise SceneError([f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]) from exc
    # Duration §5: "the scene lasts as long as its narration ... if it is shorter than the
    # last beat, loading warns and the scene is cut at the narration's end." A narration
    # shorter than an authored shot's own start (e.g. 8s vs. a shot starting at 9.7s) must
    # not turn into a structural failure here — that's exactly the "cut" case scene_warnings
    # exists to report. So the override propagates to anchors/timeline/render (everything
    # downstream keeps using the narration duration), but _check() validates shot windows
    # against the scene's AUTHORED duration (from the file, or None for inline scenes) —
    # the structure the author actually wrote — not the possibly-shorter narration.
    authored_duration = scene.duration
    if duration is not None:
        scene = scene.model_copy(update={"duration": duration})
    scene = _resolve_anchors(scene, narration)
    # R15b: a *longer* narration must not false-fail a sentence anchor that resolves (against
    # the override) past the authored end — the spec's "if the narration is longer, the last
    # shot holds, still boiling" means the last shot's window should stretch to cover it. So
    # check against whichever is longer. No override at all (duration is None): keep checking
    # against the authored duration exactly, unchanged. Override given but the scene declares
    # no authored duration (inline scene): stay unbounded, as before.
    if duration is None:
        check_duration = authored_duration
    elif authored_duration is None:
        check_duration = None
    else:
        check_duration = max(authored_duration, duration)
    problems = _check(scene.model_copy(update={"duration": check_duration}), bank)
    if problems:
        raise SceneError(problems)
    return scene


def scene_warnings(scene: ToonScene, duration: float) -> list[str]:
    last = max((sh.at + b.at + b.over for sh in scene.shots for b in sh.beats
                if isinstance(b.at, float)), default=0.0)
    last = max(last, scene.shots[-1].at)
    if last > duration:
        return [f"scene {scene.id}: its last beat ends at {last:g}s but the narration ends at "
                f"{duration:g}s; the clip will be cut there"]
    return []


def scenes_root() -> Path:
    return default_root().parent / "scenes"


def read_scene(ref: str) -> dict:
    path = Path(ref)
    if not (path.suffix in (".yaml", ".yml") and path.exists()):
        path = scenes_root() / f"{ref}.yaml"
    if not path.exists():
        raise SceneError([f"scene file not found: {path}"])
    return yaml.load(path.read_text(), Loader=_SceneLoader)


def scene_data_from_visual(visual: dict) -> dict:
    if visual.get("scene"):
        return read_scene(str(visual["scene"]))
    if visual.get("shots"):
        return {"id": visual.get("id", "inline"), "cast": visual.get("cast", {}),
                "shots": visual["shots"], "duration": visual.get("duration")}
    raise SceneError(["visual: a toon visual needs scene: <id> or inline cast + shots"])
