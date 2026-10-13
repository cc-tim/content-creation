"""The scene contract's seam (E11): what a scene is checked against.

A catalog is one engine's names (characters, sets and spots, cameras, poses, expressions, props,
icons) plus that engine's `Capabilities`: what it renders. `toon.scene` checks every scene through
the `SceneCatalog` protocol and never imports an engine's bank or drawing code. The 2.5D bank
(`toon.bank.Bank`) satisfies the protocol; toy3d's bank builds a `Catalog`.

Both engines' capability tables live here, because an engine-relative error names the engine that
does render the field ("toy3d doesn't render bob on a move beat (toon2d does)").
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import NamedTuple, Protocol, runtime_checkable

ENGINES = ("toon2d", "toy3d")
DEFAULT_ENGINE = "toon2d"
VERBS = ("door", "move", "pose", "face", "prop", "show", "hide", "camera")
SHOW_KINDS = ("speed_lines", "bubble", "anger", "x_card", "check_pill")
PROP_BEAT_FLAGS = ("flicker", "blink", "out")


class PropKind(NamedTuple):
    """What a prop kind takes and honours; anything else would load and be silently ignored."""
    needs: frozenset[str]   # use fields it needs
    draws: frozenset[str]   # use fields it draws
    states: frozenset[str]  # states a `to:` beat animates
    flags: frozenset[str]   # beat flags it honours


@dataclass(frozen=True)
class Capabilities:
    """What one engine renders. A scene field outside it fails at load, naming the engine."""
    engine: str
    verbs: frozenset[str]
    # Per verb: the optional beat fields the engine reads. On top of the table: `ease` and `bob`
    # need `over:`, and a prop beat's over/ease only time a `to:` change.
    beat_fields: Mapping[str, frozenset[str]]
    prop_kinds: Mapping[str, PropKind]
    show_kinds: frozenset[str]
    place_fields: frozenset[str]   # optional Place fields: layer, loop
    fx_kinds: frozenset[str]
    scene_fields: frozenset[str]   # optional scene-level render options: boil


_FLAGS = frozenset(PROP_BEAT_FLAGS)
_IDEA_BULB = PropKind(frozenset({"on"}), frozenset({"on", "b"}), frozenset({"b"}), _FLAGS)

# The 2.5D cairo engine (E9; the backup style): Sprint 11's tables.
TOON2D = Capabilities(
    engine="toon2d",
    verbs=frozenset(VERBS),
    beat_fields={
        "door": frozenset({"over", "ease"}),
        "move": frozenset({"over", "ease", "to", "bob"}),
        "pose": frozenset({"over", "ease", "to", "expr"}),
        "face": frozenset({"over", "ease", "to"}),
        "prop": frozenset({"over", "ease", "to", *PROP_BEAT_FLAGS}),
        "show": frozenset({"over"}),  # the pop length
        "hide": frozenset(),
        "camera": frozenset(),
    },
    prop_kinds={
        "idea_bulb": _IDEA_BULB,
        "plate": PropKind(frozenset({"held_by"}), frozenset({"held_by"}), frozenset(), frozenset()),
        "plate_stack": PropKind(frozenset({"count"}), frozenset({"count"}), frozenset({"count"}), frozenset()),
    },
    show_kinds=frozenset(SHOW_KINDS),
    place_fields=frozenset({"layer", "loop"}),
    fx_kinds=frozenset({"glow"}),
    scene_fields=frozenset({"boil"}),
)

# The 3D toy engine (E11 v0, the locked look). Narrow on purpose: only what the r7-3d tryout
# draws. No `bob` (the walk has its own step cycle), only the idea bulb, only the bubble
# (dirty plates + "!"), pose loops but no 2.5D `layer`, no fx, no line boil.
TOY3D = Capabilities(
    engine="toy3d",
    verbs=frozenset(VERBS),
    beat_fields={**TOON2D.beat_fields, "move": frozenset({"over", "ease", "to"})},
    prop_kinds={"idea_bulb": _IDEA_BULB},
    show_kinds=frozenset({"bubble"}),
    place_fields=frozenset({"loop"}),
    fx_kinds=frozenset(),
    scene_fields=frozenset(),
)

CAPABILITIES: Mapping[str, Capabilities] = {"toon2d": TOON2D, "toy3d": TOY3D}


@runtime_checkable
class SceneCatalog(Protocol):
    """What `load_scene` checks a scene against: one engine's names and capabilities."""

    @property
    def capabilities(self) -> Capabilities: ...
    @property
    def characters(self) -> Collection[str]: ...
    @property
    def sets(self) -> Collection[str]: ...
    @property
    def cameras(self) -> Collection[str]: ...
    @property
    def props(self) -> Collection[str]: ...
    @property
    def icons(self) -> Collection[str]: ...
    def spots(self, set_name: str) -> Collection[str]: ...
    def pose_class(self, character: str, pose: str) -> str | None: ...   # None: no such pose
    def expressions_of(self, character: str) -> Collection[str]: ...
    def prop_kind(self, prop: str) -> str: ...


@dataclass(frozen=True)
class Catalog:
    """A `SceneCatalog` from plain names (toy3d's bank builds one; tests use one)."""
    capabilities: Capabilities
    characters: frozenset[str]
    set_spots: Mapping[str, frozenset[str]]
    cameras: frozenset[str]
    prop_items: Mapping[str, str]                 # bank prop name -> prop kind
    icons: frozenset[str]
    poses: Mapping[str, Mapping[str, str]]        # character -> pose -> class (sit / stand)
    expressions: Mapping[str, frozenset[str]]     # character -> expression names

    @property
    def sets(self) -> Collection[str]:
        return self.set_spots.keys()

    @property
    def props(self) -> Collection[str]:
        return self.prop_items.keys()

    def spots(self, set_name: str) -> Collection[str]:
        return self.set_spots[set_name]

    def pose_class(self, character: str, pose: str) -> str | None:
        return self.poses.get(character, {}).get(pose)

    def expressions_of(self, character: str) -> Collection[str]:
        return self.expressions.get(character, frozenset())

    def prop_kind(self, prop: str) -> str:
        return self.prop_items[prop]


def load_catalog(engine: str) -> SceneCatalog:
    """The catalog a scene of `engine` is checked against: that engine's bank."""
    from toon.scene import SceneError  # toon.scene imports this module at load time

    if engine == "toon2d":
        from toon.bank import load_bank
        return load_bank()
    if engine == "toy3d":
        from toy3d.bank import load_bank as load_toy3d_bank
        return load_toy3d_bank().catalog
    raise SceneError([f"engine: unknown engine {engine!r} (engines: {', '.join(ENGINES)})"])
