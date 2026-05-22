import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from pipeline.composer.callout import (
    BASE_LABEL_GAP,
    DEFAULT_MAX_ROWS,
    ROW_HEIGHT,
    Callout,
    CalloutPlacementError,
    PlacedCallout,
    place_callouts,
)


# Deterministic measure: 10 px per char. Keeps geometry tests independent of
# installed fonts.
def _measure(label: str) -> int:
    return 10 * len(label)


_GEO = dict(left=100, right=1180, body_top=300, top_limit=120)


def test_single_callout_sits_on_bottom_row_no_leader():
    placed = place_callouts([Callout(x=600, label="1990")], measure=_measure, **_GEO)
    assert len(placed) == 1
    p = placed[0]
    assert isinstance(p, PlacedCallout)
    assert p.row == 0
    assert p.needs_leader is False
    # bottom row top-y = body_top - BASE_LABEL_GAP - ROW_HEIGHT
    assert p.y == _GEO["body_top"] - BASE_LABEL_GAP - ROW_HEIGHT
    # centered on its anchor (width = 40), clamped within [left, right-width]
    assert p.x == 600 - 40 // 2
    assert p.anchor_x == 600


def test_two_overlapping_callouts_dodge_to_second_row():
    # Two anchors 20px apart with 40px labels overlap horizontally -> second dodges up.
    placed = place_callouts(
        [Callout(x=600, label="1995"), Callout(x=620, label="1997")],
        measure=_measure, **_GEO,
    )
    rows = sorted(p.row for p in placed)
    assert rows == [0, 1]
    dodged = next(p for p in placed if p.row == 1)
    assert dodged.needs_leader is True
    assert dodged.y == _GEO["body_top"] - BASE_LABEL_GAP - 2 * ROW_HEIGHT


def test_far_apart_callouts_both_stay_bottom_row():
    placed = place_callouts(
        [Callout(x=200, label="1990"), Callout(x=1000, label="2014")],
        measure=_measure, **_GEO,
    )
    assert {p.row for p in placed} == {0}
    assert all(p.needs_leader is False for p in placed)


def test_label_clamped_within_horizontal_bounds():
    # Anchor at the far right; label must not run past `right`.
    placed = place_callouts([Callout(x=1180, label="VOLUNTARY")], measure=_measure, **_GEO)
    p = placed[0]
    assert p.x + _measure("VOLUNTARY") <= _GEO["right"]
    assert p.x >= _GEO["left"]


def test_budget_exhaustion_raises():
    # More same-x labels than DEFAULT_MAX_ROWS rows cannot fit.
    callouts = [Callout(x=600, label=f"L{i}") for i in range(DEFAULT_MAX_ROWS + 3)]
    with pytest.raises(CalloutPlacementError, match="within"):
        place_callouts(callouts, measure=_measure, **_GEO)


def test_max_rows_capped_by_header_space():
    # top_limit close to body_top leaves room for only 1 row; 2 stacked anchors -> raise.
    tight = dict(
        left=100, right=1180, body_top=300,
        top_limit=300 - BASE_LABEL_GAP - ROW_HEIGHT,
    )
    with pytest.raises(CalloutPlacementError):
        place_callouts(
            [Callout(x=600, label="1995"), Callout(x=610, label="1997")],
            measure=_measure, **tight,
        )


def test_results_sorted_and_stable():
    a = place_callouts([Callout(x=300, label="A"), Callout(x=305, label="B")],
                       measure=_measure, **_GEO)
    b = place_callouts([Callout(x=305, label="B"), Callout(x=300, label="A")],
                       measure=_measure, **_GEO)
    assert [(p.label, p.row, p.x, p.y) for p in a] == [(p.label, p.row, p.x, p.y) for p in b]
