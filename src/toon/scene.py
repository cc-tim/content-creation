"""Scene files: shots of bank items + timed beats. Wordless by construction (icon names only)."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

# The contract checks scenes through a SceneCatalog (toon.catalog): it never imports an engine's
# bank or drawing code. Each engine's capability tables (beat fields, prop kinds, …) live there.
from toon.catalog import (
    DEFAULT_ENGINE,
    PROP_BEAT_FLAGS,
    SHOW_KINDS,
    VERBS,
    Capabilities,
    SceneCatalog,
    load_catalog,
)

Ease = Literal["linear", "smooth", "out", "back"]
CARD_KINDS = ("x_card", "check_pill")
PROP_USE_FIELDS = ("on", "held_by", "b", "count")
# Why a verb takes no timing: the reason an over:/ease: on it fails with.
_UNTIMED = {"camera": "a camera beat is a cut to a new preset",
            "hide": "a hide beat is instant",
            "show": "a show beat pops in, and only over: (the pop length) times it"}


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
    """Problems with a scene, each `<path>: <message>`. `source` names where the scene came
    from (a scene file, or a storyboard scene) and prefixes every problem."""

    def __init__(self, problems: list[str], source: str | None = None):
        self.problems, self.source = problems, source
        super().__init__("; ".join(f"{source}: {p}" if source else p for p in problems))


class NeedsNarration(SceneError):
    """Sentence anchors with no narration (or no duration) to resolve them against."""


class SceneData(dict[str, Any]):
    """Scene data plus where it came from, which `load_scene` names in every error."""

    def __init__(self, data: dict, source: str | None):
        super().__init__(data)
        self.source = source


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SentenceAnchor(_Strict):
    sentence: int = Field(ge=1)
    plus: float = Field(default=0.0, ge=0.0)  # seconds after the sentence starts


class Place(_Strict):
    spot: str
    pose: str
    expr: str = "neutral"
    # Optional render fields are None when not given, so "set" means "not None" (an engine that
    # doesn't render one rejects it). layer: low puts the whole character behind the set's mid
    # layer (None: split). loop: the pose's gesture loop (None: on).
    layer: Literal["split", "low"] | None = None
    loop: bool | None = None


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
    id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")  # a card's key; never drawn

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
    over: float = Field(gt=0)  # a blink of 0 s or less would never show


class Beat(_Strict):
    """One timed change within a shot, with exactly one verb.

    `camera: <preset>` is a cut to another bank camera preset at `at`, not a blend: the new
    preset's own push/truck/punch restarts from the beat, so `over`/`ease` are rejected on it.
    Optional fields are None when not given; BEAT_FIELDS says which ones each verb reads.
    """

    at: float | SentenceAnchor
    # None: not given (instant; a show pops in over 0.25 s). 0 is instant, a show included.
    over: float | None = Field(default=None, ge=0)
    ease: Ease | None = None    # None: not given (smooth)
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
    bob: float | None = None
    flicker: Flicker | bool | None = None
    blink: Blink | None = None
    out: Literal[True] | None = None  # `out: false` would do nothing, so only true is taken

    @model_validator(mode="after")
    def _one_verb(self):
        verbs = [v for v in VERBS if getattr(self, v) is not None]
        if len(verbs) != 1:
            raise ValueError(f"a beat needs exactly one verb of {VERBS}, got {verbs or 'none'}")
        return self

    @property
    def verb(self) -> str:
        return next(v for v in VERBS if getattr(self, v) is not None)


BEAT_OPTIONAL = tuple(f for f in Beat.model_fields if f != "at" and f not in VERBS)


class Shot(_Strict):
    at: float | SentenceAnchor  # seconds into the scene, or a sentence anchor (resolved at load)
    set: str
    camera: str
    place: dict[str, Place]
    props: dict[str, PropUse] = {}
    fx: list[Fx] = []
    beats: list[Beat] = []


class ToonScene(_Strict):
    id: str
    engine: Literal["toon2d", "toy3d"] = DEFAULT_ENGINE  # toon.catalog.ENGINES; picks the catalog
    duration: float | None = None
    cast: dict[str, str]
    shots: list[Shot] = Field(min_length=1)
    boil: Literal["full", "soft", "still"] | None = None  # overrides the bank style's default
    # Set by load_scene, never authored or serialised (so never in the clip's cache key): the
    # authored duration and each shot's authored start, for the drift warning and `toon validate`.
    _authored_duration: float | None = PrivateAttr(default=None)
    _shot_starts: tuple[float | SentenceAnchor, ...] = PrivateAttr(default=())

    @property
    def authored_duration(self) -> float | None:
        return self._authored_duration

    @property
    def authored_shot_starts(self) -> tuple[float | SentenceAnchor, ...]:
        return self._shot_starts


def graphic_key(show: Show) -> str:
    """`<kind>:<target>` — the name a `hide:` beat uses. Keyed on the show's own kind, so a
    stray field of another kind can never pick the target. A card's target is its `id:` when it
    has one, so two cards with one icon get two keys."""
    target = {"speed_lines": show.speed_lines, "bubble": show.from_, "anger": show.anger,
              "x_card": show.x_card, "check_pill": show.check_pill}[show.kind]
    if show.kind in CARD_KINDS and show.id is not None:
        target = show.id
    return f"{show.kind}:{target}"


def shot_length(scene: ToonScene, i: int) -> float:
    if i + 1 < len(scene.shots):
        return float(scene.shots[i + 1].at) - float(scene.shots[i].at)
    return scene.duration - float(scene.shots[i].at) if scene.duration is not None else math.inf


# A terminator run, then any closing quotes or brackets right after it: they belong to the
# sentence they close (spec §11.2 b2), so no sentence starts with a closer.
_BREAK = re.compile(r"([.!?。！？…]+)([」』”’）)\]】》〉»›\"']*)")
# A "." after one of these words, or after a one-letter word (U.S., J. K., e.g., a.m.; not the
# pronoun "I"), is an abbreviation, not a break. en + es-419 (EE. UU., Dra., Ud.). The known
# cost: "…moved to the U.S. Then…" stays one sentence; `pipeline toon validate --narration`
# prints the split. Words are Latin letters with accents (día, camión), never CJK, so 他在U.S.
# still reads "U" as a one-letter word.
ABBREVIATIONS = frozenset({"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc",
                           "sr", "sra", "srta", "dra", "ud", "uds", "ee", "uu"})
_WORD_BEFORE = re.compile(r"(?<![A-Za-zÀ-ɏ])[A-Za-zÀ-ɏ]+$")


def _closers(found: str, sentence: str) -> str:
    """The closers right after a terminator that close something in this sentence. A straight "
    is ambiguous: it closes only an unmatched opening " (in 他走了。"你好。" it opens the next one)."""
    open_quote = sentence.count('"') % 2 == 1
    for i, ch in enumerate(found):
        if ch == '"':
            if not open_quote:
                return found[:i]
            open_quote = False
    return found


def _abbreviation(before: str) -> bool:
    m = _WORD_BEFORE.search(before)
    return m is not None and ((len(m.group()) == 1 and m.group() != "I") or m.group().lower() in ABBREVIATIONS)


def split_sentences(narration: str) -> list[str]:
    """The narration's sentences, as `at: {sentence: n}` anchors count them.

    A run of terminators is one break ("What?!", "他走了。……"), and the closing quotes right
    after it stay with it (「我走了。」). A lone "." between digits is a decimal point ("3.5"), and
    one after an abbreviation ("U.S.", "Dr.") is no break. An ellipsis ("……", "...") followed
    directly by more text is a pause inside the sentence ("我……不知道。"); followed by a space,
    the end, or a closing quote (「我不知道……」他沉默了。), it ends the sentence.
    """
    text = narration.strip()
    parts, start = [], 0
    for m in _BREAK.finditer(text):
        run, closers = m.group(1), _closers(m.group(2), text[start:m.start()])
        end = m.start(2) + len(closers)
        before, nxt = text[:m.start()], text[end:end + 1]
        if run == "." and before[-1:].isdigit() and nxt.isdigit():
            continue
        if set(run) <= {".", "…"} and run != "." and not closers and nxt and not nxt.isspace():
            continue
        if run == "." and _abbreviation(before):
            continue
        parts.append(text[start:end])
        start = end
    parts.append(text[start:])
    return [s.strip() for s in parts if s.strip()]


def sentence_starts(narration: str, duration: float) -> list[float]:
    parts = split_sentences(narration)
    total = sum(len(s) for s in parts) or 1
    starts, acc = [], 0
    for s in parts:
        starts.append(duration * acc / total)
        acc += len(s)
    return starts


def anchor_text(at: float | SentenceAnchor) -> str:
    """An `at:` as the author wrote it, for messages and `toon validate`."""
    if isinstance(at, SentenceAnchor):
        return f"{{sentence: {at.sentence}" + (f", plus: {at.plus:g}" if at.plus else "") + "}"
    return f"{at:g}s"


def _shot_order(shots: list[Shot], starts: list[float]) -> list[str]:
    """After anchors resolve, the first shot starts at 0 and shot starts strictly increase.
    Each problem names the shot, its anchor as authored and its resolved time."""
    def label(i: int) -> str:
        at = shots[i].at
        return f"{anchor_text(at)} → {starts[i]:.2f}s" if isinstance(at, SentenceAnchor) else anchor_text(at)

    p = [f"shots[0].at: {label(0)}; the first shot must start at 0"] if starts[0] != 0 else []
    p += [f"shots[{i}].at: {label(i)} is not after shots[{i - 1}] at {label(i - 1)}; "
          f"shots must start in increasing order"
          for i in range(1, len(starts)) if starts[i] <= starts[i - 1]]
    return p


def _resolve_anchors(scene: ToonScene, narration: str | None) -> ToonScene:
    """Sentence anchors → seconds: shots first (sentence start + plus), then each beat relative
    to its shot's resolved start. Every anchor resolves through sentence_starts(), the seam where
    measured word timings (E9 item 3) plug in later. Seconds stay as written: nothing stretches."""
    anchored = [f"shots[{i}].at" for i, sh in enumerate(scene.shots) if isinstance(sh.at, SentenceAnchor)]
    anchored += [f"shots[{i}].beats[{j}].at" for i, sh in enumerate(scene.shots)
                 for j, b in enumerate(sh.beats) if isinstance(b.at, SentenceAnchor)]
    if anchored and (not narration or scene.duration is None):
        raise NeedsNarration([f"{a}: sentence anchors need the scene's narration and duration" for a in anchored])
    starts = sentence_starts(narration, scene.duration) if anchored else []
    problems: list[str] = []

    def resolve(at: float | SentenceAnchor, where: str) -> float:
        if not isinstance(at, SentenceAnchor):
            return at
        if at.sentence > len(starts):
            problems.append(f"{where}: sentence {at.sentence}, but narration has {len(starts)}")
            return math.nan
        return starts[at.sentence - 1] + at.plus

    shot_at = [resolve(sh.at, f"shots[{i}].at") for i, sh in enumerate(scene.shots)]
    if problems:
        raise SceneError(problems)
    problems += _shot_order(scene.shots, shot_at)
    if problems:
        raise SceneError(problems)
    if not anchored:
        return scene
    shots = []
    for i, sh in enumerate(scene.shots):
        beats = [b if not isinstance(b.at, SentenceAnchor) else
                 b.model_copy(update={"at": resolve(b.at, f"shots[{i}].beats[{j}].at") - shot_at[i]})
                 for j, b in enumerate(sh.beats)]
        shots.append(sh.model_copy(update={"at": shot_at[i], "beats": beats}))
    if problems:
        raise SceneError(problems)
    return scene.model_copy(update={"shots": shots})


def _check(scene: ToonScene, catalog: SceneCatalog, shot_starts: tuple[float | SentenceAnchor, ...] = (),
           narration_duration: float | None = None) -> list[str]:
    """`shot_starts` are the shots' starts as authored; when any is a sentence anchor, the shot
    windows depend on the narration, so a beat outside its shot names the window at this one."""
    p: list[str] = []
    caps = catalog.capabilities
    anchored = any(isinstance(at, SentenceAnchor) for at in shot_starts)
    for who, char in scene.cast.items():
        if char not in catalog.characters:
            p.append(f"cast.{who}: unknown character {char!r} (bank has {sorted(catalog.characters)})")
    for i, shot in enumerate(scene.shots):  # shot order is checked as anchors resolve
        w = f"shots[{i}]"
        known_set = shot.set in catalog.sets
        spots = catalog.spots(shot.set) if known_set else ()
        if not known_set:
            p.append(f"{w}.set: unknown set {shot.set!r} (bank has {sorted(catalog.sets)})")
        if shot.camera not in catalog.cameras:
            p.append(f"{w}.camera: unknown camera {shot.camera!r} (bank has {sorted(catalog.cameras)})")
        for who, pl in shot.place.items():
            pw = f"{w}.place.{who}"
            if who not in scene.cast:
                p.append(f"{pw}: not in cast")
            character = scene.cast.get(who, "")
            if known_set and pl.spot not in spots:
                p.append(f"{pw}.spot: unknown spot {pl.spot!r} in set {shot.set!r}")
            if catalog.pose_class(character, pl.pose) is None:
                p.append(f"{pw}.pose: unknown pose {pl.pose!r}")
            if pl.expr not in catalog.expressions_of(character):
                p.append(f"{pw}.expr: unknown expression {pl.expr!r}")
        for name, pu in shot.props.items():
            uw = f"{w}.props.{name}"
            if pu.kind not in catalog.props:
                p.append(f"{uw}.kind: unknown prop {pu.kind!r}")
            else:
                p += _check_prop_use(pu, uw, catalog.prop_kind(pu.kind), caps)
            for field, ref in (("on", pu.on), ("held_by", pu.held_by)):
                if ref is not None and ref not in shot.place:
                    p.append(f"{uw}.{field}: {ref!r} is not placed in this shot")
        length = shot_length(scene, i)
        for j, b in enumerate(shot.beats):
            bw = f"{w}.beats[{j}]"
            if isinstance(b.at, (int, float)) and not (0 <= b.at <= length):
                if anchored:  # a retake moved this window: say where it is now
                    start = float(shot.at)
                    p.append(f"{bw}.at: {b.at:g}s is outside the shot (0–{length:.2f}s): shot {i + 1} "
                             f"{anchor_text(shot_starts[i])} → {start:.2f}–{start + length:.2f} s at this "
                             f"narration ({narration_duration:.1f} s); anchor the beat "
                             f"(at: {{sentence: n, plus: s}}) or move it")
                else:
                    p.append(f"{bw}.at: {b.at:g}s is outside the shot (0–{length:g}s)")
            p += _check_beat(b, bw, scene, shot, spots, catalog)
        p += _check_graphics(shot, w)
    return p


def _check_graphics(shot: Shot, w: str) -> list[str]:
    """Shows and hides in the order the timeline plays them (by time, then as listed). A show
    whose key is still visible would silently replace that graphic; a hide must take one down."""
    p: list[str] = []
    beats = sorted(enumerate(shot.beats), key=lambda jb: float(jb[1].at))
    shows = {j: graphic_key(b.show) for j, b in beats if b.verb == "show"}
    visible: dict[str, int] = {}  # key -> the show beat that put it up
    gone: dict[str, int] = {}     # key -> the hide beat that took it down
    for j, b in beats:
        bw = f"{w}.beats[{j}]"
        if b.verb == "show":
            key = shows[j]
            if key in visible:
                hint = ", or give each card its own id:" if b.show.kind in CARD_KINDS else ""
                p.append(f"{bw}.show: {key!r} is still showing from {w}.beats[{visible[key]}]; "
                         f"hide it first{hint}")
            visible[key] = j
            gone.pop(key, None)
        elif b.verb == "hide":
            if b.hide in visible:
                del visible[b.hide]
                gone[b.hide] = j
            elif b.hide in gone:
                p.append(f"{bw}.hide: {b.hide!r} is already hidden by {w}.beats[{gone[b.hide]}]")
            elif b.hide in shows.values():
                first, k = min((float(shot.beats[k].at), k) for k, key in shows.items() if key == b.hide)
                if first == float(b.at):  # same time: the timeline plays beats as listed
                    p.append(f"{bw}.hide: {b.hide!r} is shown at {first:g}s by {w}.beats[{k}], listed after "
                             f"this hide at the same time; list the hide after it")
                else:
                    p.append(f"{bw}.hide: {b.hide!r} was shown at {first:g}s, after this hide at {float(b.at):g}s")
            else:
                p.append(f"{bw}.hide: {b.hide!r} does not match a graphic shown earlier in this shot "
                         f"(shown: {sorted(set(shows.values()))})")
    return p


def _a(kind: str) -> str:
    return f"an {kind}" if kind[0] in "aeiou" else f"a {kind}"


def _check_prop_use(pu: PropUse, uw: str, kind: str, caps: Capabilities) -> list[str]:
    if kind not in caps.prop_kinds:
        return []
    need, draws = caps.prop_kinds[kind][:2]
    p: list[str] = []
    for field in PROP_USE_FIELDS:
        value = getattr(pu, field)
        if value is None and field in need:
            p.append(f"{uw}.{field}: {_a(kind)} prop needs {field}:")
        elif value is not None and field not in draws:
            p.append(f"{uw}.{field}: not valid on {_a(kind)} prop (it takes {sorted(draws)})")
    return p


def _check_beat(b: Beat, bw: str, scene: ToonScene, shot: Shot, spots, catalog: SceneCatalog) -> list[str]:
    p: list[str] = []
    caps = catalog.capabilities
    placed = shot.place
    v = b.verb
    pu = shot.props.get(b.prop) if v == "prop" else None
    kind = catalog.prop_kind(pu.kind) if pu is not None and pu.kind in catalog.props else None
    if kind is not None and kind not in caps.prop_kinds:
        kind = None
    if v == "move":
        if b.move not in placed:
            p.append(f"{bw}.move: {b.move!r} is not placed in this shot")
        if not isinstance(b.to, str) or b.to not in spots:
            p.append(f"{bw}.to: unknown spot {b.to!r}")
    elif v == "pose":
        if b.pose not in placed:
            p.append(f"{bw}.pose: {b.pose!r} is not placed in this shot")
        elif b.to is not None:
            character = scene.cast.get(b.pose, "")
            to_class = catalog.pose_class(character, b.to) if isinstance(b.to, str) else None
            from_class = catalog.pose_class(character, placed[b.pose].pose)
            if to_class is None:
                p.append(f"{bw}.to: unknown pose {b.to!r}")
            elif from_class is not None and to_class != from_class:
                p.append(f"{bw}.to: pose {b.to!r} changes hip ({from_class} → {to_class}); "
                         f"cut to a new shot instead")
        if b.expr is not None and b.expr not in catalog.expressions_of(scene.cast.get(b.pose, "")):
            p.append(f"{bw}.expr: unknown expression {b.expr!r}")
        if b.to is None and b.expr is None:
            p.append(f"{bw}: a pose beat needs to: <pose> and/or expr: <expression>")
    elif v == "face":
        if b.face not in placed or not isinstance(b.to, str) or b.to not in placed:
            p.append(f"{bw}: face needs two characters placed in this shot")
    elif v == "prop":
        if pu is None:
            p.append(f"{bw}.prop: unknown prop use {b.prop!r} in this shot")
        if isinstance(b.to, str):
            p.append(f"{bw}.to: prop beats take a mapping like {{b: 0.3}}")
        elif b.to == {}:
            p.append(f"{bw}.to: is empty; a prop beat animates a state like {{b: 0.3}}")
        elif isinstance(b.to, dict) and kind is not None:
            states = caps.prop_kinds[kind].states
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
        if s.at is not None and s.kind not in CARD_KINDS:
            p.append(f"{bw}.show.at: only valid with an x_card or check_pill show")
        if s.id is not None and s.kind not in CARD_KINDS:
            p.append(f"{bw}.show.id: only valid with an x_card or check_pill show")
        cards = [x for x in (s.x_card, s.check_pill) if x]
        icons = catalog.icons
        for icon in [*(s.bubble or []), *cards]:
            if icon not in icons:
                p.append(f"{bw}.show: {icon!r} is not an icon — animation is wordless; "
                         f"use one of {sorted(icons)}")
    elif v == "camera" and b.camera not in catalog.cameras:
        p.append(f"{bw}.camera: unknown camera {b.camera!r}")
    return p + _check_beat_fields(b, bw, kind, caps)


def _unread(caps: Capabilities, verb: str, field: str) -> str:
    if field in ("over", "ease") and verb in _UNTIMED:
        return f"{_UNTIMED[verb]}; {field} does not apply"
    users = [u for u, fields in caps.beat_fields.items() if field in fields]
    return f"only valid with {_a(users[0])} beat" if len(users) == 1 else f"not valid with {_a(verb)} beat"


def _check_beat_fields(b: Beat, bw: str, kind: str | None, caps: Capabilities) -> list[str]:
    """Every optional field set on a beat must be one the engine reads for its verb (and, on a
    prop beat, for its prop kind; `kind` is None when the prop doesn't resolve)."""
    p: list[str] = []
    v = b.verb
    for field in BEAT_OPTIONAL:
        if getattr(b, field) is None:
            continue
        if field not in caps.beat_fields[v]:
            p.append(f"{bw}.{field}: {_unread(caps, v, field)}")
        elif v == "prop" and field in ("over", "ease") and b.to is None:
            p.append(f"{bw}.{field}: a prop beat times only a to: change; {field} does nothing without to:")
        elif field == "ease" and not (b.over or 0.0) > 0:
            p.append(f"{bw}.ease: does nothing without over: (the change is instant)")
        elif field == "bob" and not (b.over or 0.0) > 0:
            p.append(f"{bw}.bob: needs over: (an instant move would leave a fixed lift, not a bob)")
        elif v == "prop" and field in PROP_BEAT_FLAGS and kind is not None and field not in caps.prop_kinds[kind].flags:
            takers = sorted(k for k, spec in caps.prop_kinds.items() if field in spec.flags)
            p.append(f"{bw}.{field}: {_a(kind)} prop ignores {field} (only {', '.join(takers)} takes it)")
    return p


def catalog_for(data: dict) -> SceneCatalog:
    """The catalog to load scene data against: its `engine:`'s (default toon2d). An unknown or
    unbuilt engine fails here, naming the data's source; there is never a fallback engine."""
    try:
        return load_catalog(data.get("engine", DEFAULT_ENGINE))
    except SceneError as exc:
        source = getattr(data, "source", None)
        if source is None or exc.source is not None:
            raise
        raise SceneError(exc.problems, source=source) from exc


def load_scene(data: dict, catalog: SceneCatalog, narration: str | None = None,
               duration: float | None = None, source: str | None = None) -> ToonScene:
    """Validate scene data against an engine's catalog (toon.catalog), resolving sentence
    anchors. Every SceneError names `source`, which defaults to the data's own (`read_scene`,
    `scene_data_from_visual`)."""
    source = source if source is not None else getattr(data, "source", None)
    try:
        return _load(data, catalog, narration, duration)
    except SceneError as exc:
        if source is None or exc.source is not None:
            raise
        raise type(exc)(exc.problems, source=source) from exc


def _load(data: dict, catalog: SceneCatalog, narration: str | None, duration: float | None) -> ToonScene:
    try:
        scene = ToonScene.model_validate(data)
    except ValidationError as exc:
        raise SceneError([f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]) from exc
    if scene.engine != catalog.capabilities.engine:  # every name check would be noise
        raise SceneError([f"engine: a {scene.engine} scene, but this is the "
                          f"{catalog.capabilities.engine} catalog"])
    # Duration §5: "the scene lasts as long as its narration ... if it is shorter than the
    # last beat, loading warns and the scene is cut at the narration's end." A narration
    # shorter than an authored shot's own start (e.g. 8s vs. a shot starting at 9.7s) must
    # not turn into a structural failure here — that's exactly the "cut" case scene_warnings
    # exists to report. So the override propagates to anchors/timeline/render (everything
    # downstream keeps using the narration duration), but _check() validates shot windows
    # against the scene's AUTHORED duration (from the file, or None for inline scenes) —
    # the structure the author actually wrote — not the possibly-shorter narration.
    authored_duration, shot_starts = scene.duration, tuple(sh.at for sh in scene.shots)
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
    problems = _check(scene.model_copy(update={"duration": check_duration}), catalog, shot_starts,
                      duration if duration is not None else authored_duration)
    if problems:
        raise SceneError(problems)
    scene._authored_duration, scene._shot_starts = authored_duration, shot_starts
    return scene


DRIFT_TOLERANCE = 0.5  # seconds


def _numbers(ns: list[int]) -> str:
    return f"{ns[0]}–{ns[-1]}" if len(ns) > 1 and ns == list(range(ns[0], ns[-1] + 1)) else ", ".join(map(str, ns))


def drift_warnings(scene: ToonScene, duration: float) -> list[str]:
    """Shots timed in seconds stay put when the narration's length changes. A warning, not an
    error (a scene timed in seconds is legitimate): it fires when the scene has an authored
    duration, a later shot starts at an absolute time, and the narration is more than
    DRIFT_TOLERANCE off the authored duration."""
    fixed = [i + 1 for i, at in enumerate(scene.authored_shot_starts)
             if i > 0 and not isinstance(at, SentenceAnchor)]
    authored = scene.authored_duration
    if authored is None or not fixed or abs(duration - authored) <= DRIFT_TOLERANCE:
        return []
    which = f"shots {_numbers(fixed)} are" if len(fixed) > 1 else f"shot {fixed[0]} is"
    return [f"scene {scene.id}: {which} in seconds and won't follow the narration (authored "
            f"{authored:.1f} s, narration {duration:.1f} s); anchor them with `at: {{sentence: n}}`"]


def scene_warnings(scene: ToonScene, duration: float) -> list[str]:
    last = max((float(sh.at) + b.at + (b.over or 0.0) for sh in scene.shots for b in sh.beats
                if isinstance(b.at, float)), default=0.0)
    last = max(last, float(scene.shots[-1].at))
    if last > duration:
        return [f"scene {scene.id}: its last beat ends at {last:g}s but the narration ends at "
                f"{duration:g}s; the clip will be cut there"]
    return []


def scenes_root() -> Path:
    from toon.bank import default_root  # the 2.5D scene library sits beside its bank

    return default_root().parent / "scenes"


_REPO = Path(__file__).resolve().parents[2]


def source_name(path: Path) -> str:
    """A file as errors name it: repo-relative inside the repo, else as given."""
    try:
        return str(Path(path).resolve().relative_to(_REPO))
    except ValueError:
        return str(path)


def scene_path(ref: str) -> Path:
    """A scene id (`001-lioness-dishes` → assets/toon/scenes/<id>.yaml) or a path to a YAML file."""
    path = Path(ref)
    return path if path.suffix in (".yaml", ".yml") else scenes_root() / f"{ref}.yaml"


def read_scene(ref: str) -> SceneData:
    """A scene file's data, which remembers the file (`load_scene` names it in every error)."""
    path = scene_path(ref)
    src = source_name(path)
    if not path.exists():
        raise SceneError(["scene file not found"], source=src)
    try:
        data = yaml.load(path.read_text(), Loader=_SceneLoader)
    except yaml.YAMLError as exc:
        raise SceneError([f"not valid YAML: {' '.join(str(exc).split())}"], source=src) from exc
    if not isinstance(data, dict):
        raise SceneError([f"expected a scene mapping (id, cast, shots), got {type(data).__name__}"], source=src)
    return SceneData(data, src)


# Keys the pipeline owns on every storyboard visual — `type` (dispatch), the director's
# `confidence`/`rationale`, compose's `edit_mode` — never part of the toon scene itself.
PIPELINE_VISUAL_KEYS = frozenset({"type", "confidence", "rationale", "edit_mode"})
# What a `{scene: <id>}` reference may override on top of the scene file.
SCENE_REF_OVERRIDES = frozenset({"boil"})


def scene_data_from_visual(visual: dict, origin: str | None = None) -> SceneData:
    """A storyboard `toon` visual → scene data. Inline scenes pass every scene key through, so
    the scene model's `extra="forbid"` catches typos; references take `boil:` and nothing else.

    `origin` names the storyboard scene (`<storyboard file> scene <sid>`). The data's source is
    then the origin itself for an inline scene, or `<scene file> (from <origin>)` for a reference.
    """
    own = {k: v for k, v in visual.items() if k not in PIPELINE_VISUAL_KEYS}
    if own.get("scene"):
        ref = str(own["scene"])
        extra = sorted(set(own) - {"scene"} - SCENE_REF_OVERRIDES)
        if extra:
            raise SceneError([f"visual.{k}: a scene reference takes only scene: and "
                              f"{', '.join(sorted(SCENE_REF_OVERRIDES))}: (edit the scene file, "
                              f"or inline the shots)" for k in extra], source=origin)
        src = f"{source_name(scene_path(ref))} (from {origin})" if origin else None
        try:
            data = read_scene(ref)
        except SceneError as exc:
            if src is None:
                raise
            raise SceneError(exc.problems, source=src) from exc
        return SceneData({**data, **{k: own[k] for k in SCENE_REF_OVERRIDES if k in own}}, src or data.source)
    if own.get("shots"):
        return SceneData({"id": "inline", "cast": {}, **own}, origin)
    raise SceneError(["visual: a toon visual needs scene: <id> or inline cast + shots"], source=origin)
