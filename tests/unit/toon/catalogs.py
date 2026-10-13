"""Test catalogs. TOY3D_TEST stands in for the toy3d bank until E11 Sprint 12 phase 2 builds it:
the 2.5D MINI's names with the toy3d engine's capabilities, so contract cases run on both."""
from toon.catalog import TOY3D, Catalog

TOY3D_TEST = Catalog(
    capabilities=TOY3D,
    characters=frozenset({"tim", "lioness"}),
    set_spots={"office": frozenset({"desk_seat", "doorway", "doorway_out"})},
    cameras=frozenset({"front34_push", "two_shot", "close_push"}),
    prop_items={"idea_bulb": "idea_bulb"},
    icons=frozenset({"dishes", "bang"}),
    poses={"tim": {"sit_typing": "sit", "sit_shock": "sit", "stand_point": "stand"},
           "lioness": {"stand_point": "stand"}},
    expressions={"tim": frozenset({"neutral", "focused", "shocked"}),
                 "lioness": frozenset({"neutral", "angry"})},
)
