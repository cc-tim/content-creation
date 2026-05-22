"""Callout overlay primitive: collision-free placement of short labels above a
plot, with leader lines when a label is dodged off its anchor row.

Pure geometry + drawing helpers (no I/O, no network, no randomness) so output
is deterministic and golden-testable — the same contract as
``composer/chart_anim.py`` frame generators. Two chart call sites consume it:
``chart._render_line`` (static) and ``chart_anim._animate_line_frame``
(animated); both delegate marker-label placement here so they cannot drift.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ROW_HEIGHT = 22          # vertical pitch between dodge rows (px)
BASE_LABEL_GAP = 6       # gap between body_top and the bottom row's top-y
DEFAULT_MAX_ROWS = 3     # vertical dodge budget (placement, NOT runtime — two-axes)
LABEL_PAD = 6            # horizontal padding around a label for overlap tests


class CalloutPlacementError(ValueError):
    """Raised when callouts cannot be placed within the available row budget."""


@dataclass
class Callout:
    x: int          # anchor x in px (the marker column)
    label: str


@dataclass
class PlacedCallout:
    x: int          # clamped label left-x
    y: int          # label top-y
    label: str
    anchor_x: int   # original marker x (leader-line origin x)
    width: int      # measured label width (px)
    row: int        # 0 = bottom row (closest to the plot), higher = stacked upward
    needs_leader: bool


def _row_top_y(body_top: int, row: int) -> int:
    return body_top - BASE_LABEL_GAP - (row + 1) * ROW_HEIGHT


def place_callouts(
    callouts: list[Callout],
    *,
    measure: Callable[[str], int],
    left: int,
    right: int,
    body_top: int,
    top_limit: int,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> list[PlacedCallout]:
    """Place labels above ``body_top`` without horizontal overlap.

    Labels stack upward in rows of ``ROW_HEIGHT``. Each label is centered on its
    anchor x, clamped to ``[left, right]``. A label is assigned the LOWEST row
    whose horizontal span (± ``LABEL_PAD``) is free; the bottom row (0) needs no
    leader line, higher rows do. ``max_rows`` is capped so the topmost row's
    top-y never rises above ``top_limit`` (keeps labels out of the chart title).
    Raises ``CalloutPlacementError`` if a label cannot be placed.
    """
    # Cap the row budget by available header space above body_top.
    space = body_top - BASE_LABEL_GAP - top_limit
    space_rows = max(1, space // ROW_HEIGHT)
    budget = max(1, min(max_rows, space_rows))

    occupied: dict[int, list[tuple[int, int]]] = {r: [] for r in range(budget)}
    placed: list[PlacedCallout] = []

    for c in sorted(callouts, key=lambda c: (c.x, c.label)):
        w = measure(c.label)
        x_left = max(left, min(right - w, c.x - w // 2))
        span = (x_left - LABEL_PAD, x_left + w + LABEL_PAD)
        for row in range(budget):
            if all(span[1] <= s or span[0] >= e for (s, e) in occupied[row]):
                occupied[row].append(span)
                placed.append(
                    PlacedCallout(
                        x=x_left,
                        y=_row_top_y(body_top, row),
                        label=c.label,
                        anchor_x=c.x,
                        width=w,
                        row=row,
                        needs_leader=row != 0,
                    )
                )
                break
        else:
            raise CalloutPlacementError(
                f"cannot place callout {c.label!r} within {budget} rows "
                f"(reduce marker count or widen the chart)"
            )

    return placed


def _draw_placed_callouts(
    draw: Any,
    placed: list[PlacedCallout],
    *,
    ink: tuple[int, int, int],
    muted: tuple[int, int, int],
    font: Any,
    leader_from_y: int,
) -> None:
    """Draw labels + leader lines onto a caller-supplied ImageDraw (pure)."""
    for p in placed:
        if p.needs_leader:
            label_cx = p.x + p.width // 2
            label_bottom = p.y + ROW_HEIGHT
            draw.line([(p.anchor_x, leader_from_y), (label_cx, label_bottom)],
                      fill=muted, width=1)
        draw.text((p.x, p.y), p.label, font=font, fill=ink)


def render_callouts(
    callouts: list[Callout],
    base_image: Any,
    *,
    left: int,
    right: int,
    body_top: int,
    top_limit: int,
    leader_from_y: int,
    ink: tuple[int, int, int],
    muted: tuple[int, int, int],
    font_size: int = 18,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> Any:
    """Composite callouts onto a copy of ``base_image`` and return it.

    Primarily the golden-test surface (chart call sites use ``place_callouts`` +
    ``_draw_placed_callouts`` directly because they own a shared ``ImageDraw``).
    """
    from PIL import ImageDraw

    from pipeline.composer.rich_slide import _SANS_BOLD, _load_font

    font = _load_font(_SANS_BOLD, font_size)
    img = base_image.copy()
    draw = ImageDraw.Draw(img)
    placed = place_callouts(
        callouts,
        measure=lambda s: int(draw.textlength(s, font=font)),
        left=left, right=right, body_top=body_top, top_limit=top_limit,
        max_rows=max_rows,
    )
    _draw_placed_callouts(draw, placed, ink=ink, muted=muted, font=font,
                          leader_from_y=leader_from_y)
    return img
