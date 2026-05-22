"""Chart renderer: styled-editorial data graphics (not a Plotly dashboard).

Two-pass like ``rich_slide.py``: an optional AI background (Flux draft, cached by
``md5(prompt)`` under ``work_dir/image_cache/``) + a Pillow composite of the data.
Five static chart_types: stat_big_number, proportion_blocks, timeline, bar, comparison.

Charts carry their own title text; the ``open_book_page`` frame is applied later at
compose time (``composer/frame.py``), so this renderer does NOT wrap the frame itself.
The bottom 25% of the canvas is reserved for burned narration subtitles (mirrors
``rich_slide.py``), so all chart body content stays above ``_BODY_BOTTOM_FRAC``.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.base import image_to_video
from pipeline.composer.callout import (
    Callout,
    CalloutPlacementError,
    _draw_placed_callouts,
    place_callouts,
)
from pipeline.composer.rich_slide import (
    _SANS_BOLD,
    _SANS_REGULAR,
    _SERIF_BOLD,
    _load_font,
    _wrap_text,
)
from pipeline.errors import SceneRenderError
from pipeline.providers.base import ProviderError, try_chain
from pipeline.providers.gen_image import GenImageProvider

logger = structlog.get_logger()

CHART_TYPES = {"stat_big_number", "proportion_blocks", "timeline", "bar", "comparison", "line"}

# Warm editorial palette (book-page feel). Chart OWNS its foreground colors for v1 so
# the look is guaranteed editorial regardless of the project's (cool, slate) Theme
# defaults; full Theme-color integration is deferred to E4 (Style Manifest). The AI
# background prompt still consumes theme.image_style, which is where art-direction
# continuity lives. (Theme.secondary_bg defaults to slate-700 #334155 — cool — so
# consuming it for chart paper would defeat the editorial goal; we do not.)
_INK = (38, 30, 22)        # near-black warm ink for headlines
_PAPER = (244, 236, 222)   # aged-paper substrate
_MUTED = (120, 104, 86)    # sepia muted for captions/axes
_ACCENT = (181, 83, 42)    # warm terracotta highlight

# Bottom 25% (>= 0.75*H) is reserved for burned narration subtitles. ALL chart body
# content + the source credit stay above it.
_BODY_BOTTOM_FRAC = 0.70   # chart body must not extend past this
_CREDIT_Y_FRAC = 0.71      # source credit sits in the 0.70-0.75 gap, above subtitles
_HEADER_GAP = 24           # min vertical gap between header bottom (`top`) and body


def validate_chart_visual(
    visual: dict[str, Any],
    scene_id: str,
    duration_sec: float | None = None,
) -> list[str]:
    """Return all chart schema issues as strings; does not raise.

    The storyboard-write-time validator uses this to surface multiple problems
    in one pass. ``_validate_chart`` below wraps this and raises on the first
    issue for render-time defense-in-depth.

    When ``duration_sec`` is provided AND ``visual.animate.enabled`` is true,
    also validates the animate block (variant support, easing name, duration
    ceiling). The duration ceiling is the in-code expression of the two-axes
    rule: animation is a visual-quality lift, never a runtime extender.
    """
    issues: list[str] = []
    chart_type = visual.get("chart_type")
    if not chart_type:
        issues.append(
            f"chart {scene_id}: missing 'chart_type' (one of {sorted(CHART_TYPES)})"
        )
        return issues  # downstream schema checks need chart_type
    if chart_type not in CHART_TYPES:
        issues.append(
            f"chart {scene_id}: unknown chart_type={chart_type!r}; "
            f"use one of {sorted(CHART_TYPES)}"
        )
        return issues  # don't try schema-checks against an unknown type

    data = visual.get("data")
    if not data:
        issues.append(
            f"chart {scene_id}: missing 'data' for chart_type={chart_type!r}"
        )
        # Schema checks below would all blow up on None — return here.
        return issues + _validate_animate(visual, scene_id, chart_type, duration_sec)

    if chart_type != "timeline" and not isinstance(data, Mapping):
        issues.append(
            f"chart {scene_id}: data for chart_type={chart_type!r} must be an "
            f"object; got {data!r}"
        )
        return issues + _validate_animate(visual, scene_id, chart_type, duration_sec)

    if chart_type == "stat_big_number":
        value = str(data.get("value", ""))
        if not value:
            issues.append(f"chart {scene_id}: stat_big_number needs data.value")
        elif len(value) > 8:
            issues.append(
                f"chart {scene_id}: stat_big_number value {value!r} > 8 chars "
                f"(won't fit big serif); shorten or use a bar/timeline."
            )
    elif chart_type == "bar":
        x, y = data.get("x"), data.get("y")
        if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(y) or not x:
            issues.append(
                f"chart {scene_id}: bar data needs equal-length non-empty 'x' and 'y' "
                f"lists; got x={x!r} y={y!r}"
            )
    elif chart_type == "comparison":
        for side_name in ("left", "right"):
            side = data.get(side_name)
            if not isinstance(side, dict) or "label" not in side or "value" not in side:
                issues.append(
                    f"chart {scene_id}: comparison needs {side_name} with "
                    f"'label' and 'value'"
                )
    elif chart_type == "proportion_blocks":
        if "ratio" not in data:
            issues.append(
                f"chart {scene_id}: proportion_blocks needs data.ratio (0..1)"
            )
    elif chart_type == "timeline":
        if not isinstance(data, list) or not data:
            issues.append(
                f"chart {scene_id}: timeline data must be a non-empty list of "
                f"{{year, label}} entries"
            )
    elif chart_type == "line":
        points = data.get("points")
        if not isinstance(points, list) or not points:
            issues.append(
                f"chart {scene_id}: line data needs non-empty 'points' list of "
                f"{{x, y}} entries; got {points!r}"
            )
        else:
            for i, p in enumerate(points):
                if not isinstance(p, dict) or "x" not in p or "y" not in p:
                    issues.append(
                        f"chart {scene_id}: line points[{i}] must be {{x, y}}; got {p!r}"
                    )
        markers = data.get("markers") or []
        if not isinstance(markers, list):
            issues.append(
                f"chart {scene_id}: line 'markers' must be a list; got {markers!r}"
            )
        else:
            for i, m in enumerate(markers):
                if not isinstance(m, dict) or "x" not in m:
                    issues.append(
                        f"chart {scene_id}: line marker[{i}] must be {{x, label}}; "
                        f"got {m!r}"
                    )

    issues.extend(_validate_animate(visual, scene_id, chart_type, duration_sec))
    return issues


def _validate_animate(
    visual: dict[str, Any],
    scene_id: str,
    chart_type: str,
    duration_sec: float | None,
) -> list[str]:
    """Animate-block validation; returns issues without raising."""
    out: list[str] = []
    animate = visual.get("animate") or {}
    if not animate.get("enabled"):
        return out

    if chart_type not in {"line", "bar", "stat_big_number"}:
        out.append(
            f"chart {scene_id}: chart_type={chart_type!r} has no animated "
            f"variant (supported: line, bar, stat_big_number); set "
            f"animate.enabled=false or pick a supported chart_type"
        )
    from pipeline.composer.chart_anim import EASING, HOLD_TAIL_MIN_SEC
    easing_name = animate.get("easing", "ease_out_cubic")
    if easing_name not in EASING:
        out.append(
            f"chart {scene_id}: unknown easing {easing_name!r}; "
            f"use one of {sorted(EASING)}"
        )
    if duration_sec is not None:
        reveal = animate.get("reveal_duration_sec")
        if reveal is not None and float(reveal) > duration_sec - HOLD_TAIL_MIN_SEC:
            out.append(
                f"chart {scene_id}: reveal_duration_sec={reveal} > "
                f"duration_sec({duration_sec}) - hold_tail({HOLD_TAIL_MIN_SEC}); "
                f"shorten the reveal — animation cannot extend the scene "
                f"(two-axes rule: arsenal items do not add runtime)"
            )
    return out


def _validate_chart(
    visual: dict[str, Any],
    scene_id: str,
    duration_sec: float | None = None,
) -> None:
    """Render-time wrapper: raise on first issue. Defense-in-depth.

    The storyboard-write-time validator (``director/storyboard_validator.py``)
    should catch chart schema problems earlier via ``validate_chart_visual``;
    this wrapper ensures ``render_chart`` still fails loud if a bad chart
    slips through (e.g. a programmatic caller that bypasses the storyboard
    validator).
    """
    issues = validate_chart_visual(visual, scene_id, duration_sec=duration_sec)
    if issues:
        raise ValueError(issues[0])


def _palette(theme: dict) -> dict[str, tuple[int, int, int]]:
    # v1: fixed warm editorial palette (see module note). theme reserved for E4.
    return {"ink": _INK, "paper": _PAPER, "accent": _ACCENT, "muted": _MUTED}


def _build_background(visual, theme, width, height, work_dir, scene_id):
    """Flat themed paper (deterministic) unless an AI background is requested."""
    from PIL import Image

    pal = _palette(theme)
    if not visual.get("ai_background", True):
        return Image.new("RGB", (width, height), pal["paper"])

    bg_prompt = visual.get("background_prompt") or (
        "aged paper texture, soft sepia stains, faint grid"
    )
    image_style = theme.get("image_style", "")
    prompt = (
        f"{bg_prompt}. Style: {image_style}"
        if image_style and image_style not in bg_prompt
        else bg_prompt
    )

    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_png = cache_dir / f"{hashlib.md5(prompt.encode()).hexdigest()[:12]}.png"
    if not cached_png.exists():
        size = "1792x1024" if width > height else "1024x1792"
        try:
            try_chain(
                [GenImageProvider(tier="draft")],
                prompt=prompt,
                out_path=cached_png,
                size=size,
            )
            logger.info("chart.image_generated", scene=scene_id)
        except ProviderError as exc:
            logger.warning("chart.image_failed", scene=scene_id, error=str(exc))
            Image.new("RGB", (width, height), pal["paper"]).save(cached_png)
    else:
        logger.info("chart.image_cache_hit", scene=scene_id)

    bg = Image.open(cached_png).convert("RGB").resize((width, height), Image.LANCZOS)
    # Wash the AI background toward paper so the foreground data reads clearly.
    wash = Image.new("RGB", (width, height), pal["paper"])
    return Image.blend(bg, wash, 0.55)


def render_chart(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict | None = None,
) -> Path:
    """Render a styled-editorial chart and return the path to the .mp4 segment."""
    from PIL import ImageDraw

    theme = theme or {}
    _validate_chart(visual, scene_id, duration_sec=duration_sec)
    chart_type = visual["chart_type"]
    pal = _palette(theme)

    try:
        if (visual.get("animate") or {}).get("enabled"):
            from pipeline.composer.chart_anim import render_animated_chart
            return render_animated_chart(
                visual, duration_sec, width, height, work_dir, scene_id, theme
            )

        bg = _build_background(visual, theme, width, height, work_dir, scene_id)
        draw = ImageDraw.Draw(bg)

        top = _draw_header(draw, visual, width, height, pal)
        renderer = {
            "stat_big_number": _render_stat,
            "proportion_blocks": _render_proportion,
            "timeline": _render_timeline,
            "bar": _render_bar,
            "comparison": _render_comparison,
            "line": _render_line,
        }[chart_type]
        renderer(draw, visual, width, height, pal, top)
        _draw_credit(draw, visual, width, height, pal)

        composite_png = work_dir / f"{scene_id}_chart.png"
        bg.save(composite_png)
        output = work_dir / f"{scene_id}_visual.mp4"
        image_to_video(composite_png, output, duration_sec, width, height)
    except CalloutPlacementError as e:
        # The precise render-time fence for marker density (pin-down #2): convert
        # the geometry exception into a loud SceneRenderError so an over-dense
        # chart fails visibly with a fix hint, rather than degrading to a silent
        # black-screen scene via compose's generic exception fallback.
        raise SceneRenderError(
            scene=scene_id,
            reason=f"chart callout placement failed: {e}",
            suggested_fix="Reduce marker count or split into multiple charts.",
        ) from e
    return output


def _draw_header(draw, visual, width, height, pal) -> int:
    """Title + subtitle at the top; return the y where the chart body may start."""
    pad = int(width * 0.07)
    y = int(height * 0.09)
    title = visual.get("title", "")
    if title:
        f = _load_font(_SERIF_BOLD, 40)
        for line in _wrap_text(title, f, width - pad * 2, draw):
            draw.text((pad, y), line, font=f, fill=pal["ink"])
            y += draw.textbbox((0, 0), line, font=f)[3] + 6
    subtitle = visual.get("subtitle", "")
    if subtitle:
        f = _load_font(_SANS_REGULAR, 24)
        draw.text((pad, y), subtitle, font=f, fill=pal["muted"])
        y += 34
    draw.rectangle([pad, y + 6, pad + 70, y + 10], fill=pal["accent"])
    return y + 28


def _draw_credit(draw, visual, width, height, pal) -> None:
    credit = visual.get("source_credit")
    if not credit:
        return
    f = _load_font(_SANS_REGULAR, 20)
    txt = f"Source: {credit}"
    pad = int(width * 0.07)
    tb = draw.textbbox((0, 0), txt, font=f)
    x = width - pad - (tb[2] - tb[0])
    draw.text((x, int(height * _CREDIT_Y_FRAC)), txt, font=f, fill=pal["muted"])


def _render_stat(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    cx = width // 2
    body_top = max(top + _HEADER_GAP, int(height * 0.30))

    num_f = _load_font(_SERIF_BOLD, 150)
    value = str(data["value"])
    nb = draw.textbbox((0, 0), value, font=num_f)
    draw.text((cx - (nb[2] - nb[0]) // 2, body_top), value, font=num_f, fill=pal["accent"])
    # Advance to just below the number's actual ink bottom (nb[3]), not its height,
    # so the unit label can't ride up into the digits.
    y = body_top + nb[3] + 24

    unit = str(data.get("unit", ""))
    if unit:
        uf = _load_font(_SANS_BOLD, 36)
        ub = draw.textbbox((0, 0), unit.upper(), font=uf)
        draw.text((cx - (ub[2] - ub[0]) // 2, y), unit.upper(), font=uf, fill=pal["ink"])
        y += 52

    context = str(data.get("context", ""))
    if context:
        cf = _load_font(_SANS_REGULAR, 28)
        cb = draw.textbbox((0, 0), context, font=cf)
        draw.text((cx - (cb[2] - cb[0]) // 2, y), context, font=cf, fill=pal["muted"])


def _render_proportion(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    pad = int(width * 0.07)
    bar_w = width - pad * 2
    ratio = max(0.0, min(1.0, float(data["ratio"])))
    y0 = max(top + _HEADER_GAP, int(height * 0.38))
    bar_h = int(height * 0.15)
    split = pad + int(bar_w * ratio)

    draw.rectangle([pad, y0, split, y0 + bar_h], fill=pal["accent"])
    draw.rectangle([split, y0, pad + bar_w, y0 + bar_h], fill=pal["muted"])

    pf = _load_font(_SERIF_BOLD, 52)
    draw.text((pad + 24, y0 + bar_h // 2 - 30), f"{round(ratio * 100)}%",
              font=pf, fill=pal["paper"])

    lf = _load_font(_SANS_REGULAR, 28)
    draw.text((pad, y0 + bar_h + 22), str(data.get("label", "")), font=lf, fill=pal["ink"])
    sec = data.get("secondary_label")
    if sec:
        sb = draw.textbbox((0, 0), str(sec), font=lf)
        draw.text((pad + bar_w - (sb[2] - sb[0]), y0 + bar_h + 22),
                  str(sec), font=lf, fill=pal["muted"])


def _render_timeline(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    pad = int(width * 0.09)
    axis_y = max(top + 90, int(height * 0.52))
    span = width - pad * 2
    n = len(data)
    draw.line([pad, axis_y, pad + span, axis_y], fill=pal["muted"], width=3)

    yf = _load_font(_SERIF_BOLD, 30)
    lf = _load_font(_SANS_REGULAR, 22)
    for i, entry in enumerate(data):
        x = pad + (span * i // max(1, n - 1))
        draw.ellipse([x - 9, axis_y - 9, x + 9, axis_y + 9], fill=pal["accent"])

        year = str(entry.get("year", ""))
        yb = draw.textbbox((0, 0), year, font=yf)
        draw.text((x - (yb[2] - yb[0]) // 2, axis_y + 22), year, font=yf, fill=pal["ink"])

        label = str(entry.get("label", ""))
        lines = _wrap_text(label, lf, int(span / n) + 40, draw)
        ly = axis_y - 30 - (40 if i % 2 else 0) - len(lines) * 26
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=lf)
            draw.text((x - (lb[2] - lb[0]) // 2, ly), line, font=lf, fill=pal["muted"])
            ly += 26


def _render_bar(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    xs = data["x"]
    ys = [float(v) for v in data["y"]]
    unit = data.get("y_unit", "")
    pad = int(width * 0.07)

    label_f = _load_font(_SANS_BOLD, 26)
    val_f = _load_font(_SERIF_BOLD, 28)
    max_v = max(ys) or 1.0
    track_w = int(width * 0.62)
    y0 = max(top + _HEADER_GAP, int(height * 0.28))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    row_h = int((body_bottom - y0) / len(xs))
    bar_h = min(int(row_h * 0.42), 46)

    for label, v in zip(xs, ys, strict=False):
        draw.text((pad, y0), str(label), font=label_f, fill=pal["ink"])
        by = y0 + 34
        bw = int(track_w * (v / max_v))
        draw.rectangle([pad, by, pad + max(2, bw), by + bar_h], fill=pal["accent"])
        vtxt = f"{v:g}{unit}"
        draw.text((pad + max(2, bw) + 16, by + bar_h // 2 - 16),
                  vtxt, font=val_f, fill=pal["ink"])
        y0 += row_h


def _render_comparison(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    mid = width // 2
    y_val = max(top + _HEADER_GAP, int(height * 0.36))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    draw.line([mid, int(height * 0.30), mid, body_bottom], fill=pal["muted"], width=2)

    vf = _load_font(_SERIF_BOLD, 92)
    lf = _load_font(_SANS_REGULAR, 30)
    for side, cx, color in (
        ("left", mid // 2, pal["accent"]),
        ("right", mid + mid // 2, pal["ink"]),
    ):
        s = data[side]
        val = str(s["value"])
        vb = draw.textbbox((0, 0), val, font=vf)
        draw.text((cx - (vb[2] - vb[0]) // 2, y_val), val, font=vf, fill=color)
        lab = str(s["label"])
        lb = draw.textbbox((0, 0), lab, font=lf)
        draw.text((cx - (lb[2] - lb[0]) // 2, y_val + (vb[3] - vb[1]) + 28),
                  lab, font=lf, fill=pal["muted"])


def _render_line(draw, visual, width, height, pal, top) -> None:
    """Draw axes + falling curve through data.points + labeled markers.

    Used both as a static chart_type AND as the base for the animated variant.
    The animated frame generator re-uses this layout but masks the curve / markers
    by a progress factor.
    """
    data = visual["data"]
    points = data["points"]
    markers = data.get("markers") or []

    pad_l = int(width * 0.10)
    pad_r = int(width * 0.07)
    body_top = max(top + _HEADER_GAP, int(height * 0.30))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    plot_w = width - pad_l - pad_r
    plot_h = body_bottom - body_top

    xs = [float(p["x"]) for p in points]
    ys = [float(p["y"]) for p in points]
    marker_xs = [float(m["x"]) for m in markers if isinstance(m, dict) and "x" in m]
    # Extend the visible x-axis to encompass markers that fall outside the data
    # range (the wiki mandate: events like 1982 First study predate the data).
    x_min = min(xs + marker_xs)
    x_max = max(xs + marker_xs)
    y_max = max(ys) or 1.0
    x_span = max(1.0, x_max - x_min)

    def _to_px(x: float, y: float) -> tuple[int, int]:
        px = pad_l + int(plot_w * (x - x_min) / x_span)
        py = body_top + int(plot_h * (1.0 - y / y_max))
        return px, py

    draw.line([pad_l, body_bottom, pad_l + plot_w, body_bottom],
              fill=pal["muted"], width=2)
    draw.line([pad_l, body_top, pad_l, body_bottom], fill=pal["muted"], width=2)

    yf = _load_font(_SANS_REGULAR, 22)
    # Label the FIRST and LAST data points (not the extended axis ends), so the
    # axis labels stay anchored to real data. Placed INSIDE the plot just above
    # the axis line to keep the 0.70-0.75 strip free for the source credit.
    label_bb = draw.textbbox((0, 0), "9999", font=yf)
    label_h = label_bb[3] - label_bb[1]
    for x_label in (min(xs), max(xs)):
        s = f"{int(x_label)}"
        sb = draw.textbbox((0, 0), s, font=yf)
        px = pad_l + int(plot_w * (x_label - x_min) / x_span)
        draw.text((px - (sb[2] - sb[0]) // 2, body_bottom - label_h - 6),
                  s, font=yf, fill=pal["muted"])

    px_points = [_to_px(p["x"], p["y"]) for p in points]
    for a, b in zip(px_points, px_points[1:], strict=False):
        draw.line([a, b], fill=pal["accent"], width=4)
    for px, py in px_points:
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=pal["accent"])

    mf = _load_font(_SANS_BOLD, 18)
    callouts = []
    for m in markers:
        mx = float(m["x"])
        mpx = pad_l + int(plot_w * (mx - x_min) / x_span)
        draw.line([mpx, body_top + 8, mpx, body_bottom], fill=pal["muted"], width=1)
        draw.ellipse([mpx - 7, body_top + 1, mpx + 7, body_top + 15], fill=pal["ink"])
        callouts.append(Callout(x=mpx, label=str(m.get("label", ""))))

    placed = place_callouts(
        callouts,
        measure=lambda s: int(draw.textlength(s, font=mf)),
        left=pad_l, right=pad_l + plot_w, body_top=body_top, top_limit=top + 2,
    )
    _draw_placed_callouts(draw, placed, ink=pal["ink"], muted=pal["muted"],
                          font=mf, leader_from_y=body_top)
