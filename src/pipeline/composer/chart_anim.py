"""Animated chart reveals: pure frame generators + ffmpeg orchestrator.

Built on top of ``composer/chart.py`` (Sprint 1) and copying the multi-frame
ffmpeg pipeline from ``composer/base.py:_camera_motion_to_video``. Three animated
variants in v1: ``line`` (left-to-right curve draw with markers synced to draw
progress), ``bar`` (sequential grow with stagger), ``stat_big_number`` (digits-only
count-up with formatting preserved).

Frame generators are PURE: ``(progress, visual, base_bg, width, height, palette,
top) -> PIL.Image``. No disk, no network, no random. Identical inputs return
byte-identical images — what makes sampled-frame goldens viable.

Two-axes guardrail: ``_resolve_reveal_duration`` defaults to a fraction of the
scene duration with a ceiling; ``chart._validate_chart`` enforces
``reveal_duration_sec <= duration_sec - HOLD_TAIL_MIN_SEC`` (raises). Animation
is a visual-QUALITY lift, NOT a runtime extender.
"""
from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.callout import Callout, _draw_placed_callouts, place_callouts
from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()

FPS = 30
HOLD_TAIL_MIN_SEC = 0.5
DEFAULT_REVEAL_FRACTION = 0.6
DEFAULT_REVEAL_MAX_SEC = 5.0
BAR_STAGGER_FRAC = 0.10
_DEFAULT_EASING = "ease_out_cubic"


def _progress_linear(t: float) -> float:
    return max(0.0, min(1.0, t))


def _progress_ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


EASING: dict[str, Callable[[float], float]] = {
    "linear": _progress_linear,
    "ease_out_cubic": _progress_ease_out_cubic,
}


def _resolve_easing(visual: dict[str, Any]) -> Callable[[float], float]:
    name = (visual.get("animate") or {}).get("easing", _DEFAULT_EASING)
    if name not in EASING:
        raise ValueError(
            f"unknown easing {name!r}; use one of {sorted(EASING)}"
        )
    return EASING[name]


def _resolve_reveal_duration(visual: dict[str, Any], duration_sec: float) -> float:
    """Default to ``min(duration_sec * fraction, max)`` when absent.

    Validation of the ceiling lives in ``chart._validate_chart`` so it fires at
    compose-time, not at frame-write-time.
    """
    explicit = (visual.get("animate") or {}).get("reveal_duration_sec")
    if explicit is not None:
        return float(explicit)
    return min(duration_sec * DEFAULT_REVEAL_FRACTION, DEFAULT_REVEAL_MAX_SEC)


_DIGIT_PATTERN = re.compile(r"(\d+)")


def _count_up_value(final_value: str, progress: float) -> tuple[str, bool]:
    """Return ``(display_string, parsed_ok)``.

    Parses contiguous digit runs in ``final_value``, scales each by ``progress``,
    reapplies the surrounding non-digit characters verbatim. Empty digit match
    (no digits at all) returns ``(final_value, False)`` so the orchestrator can
    switch to a fade-in fallback.
    """
    matches = list(_DIGIT_PATTERN.finditer(final_value))
    if not matches:
        return final_value, False
    p = max(0.0, min(1.0, progress))
    out: list[str] = []
    cursor = 0
    for m in matches:
        out.append(final_value[cursor : m.start()])
        digits = m.group(1)
        scaled = int(round(int(digits) * p))
        out.append(str(scaled).zfill(len(digits)))
        cursor = m.end()
    out.append(final_value[cursor:])
    return "".join(out), True


# ── Frame generators ───────────────────────────────────────────────────────────
def _animate_line_frame(
    progress: float,
    visual: dict[str, Any],
    base_bg: Any,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    top: int,
) -> Any:
    """Draw the `line` chart up to ``progress`` of its total path length.

    At progress=0 nothing data-related is drawn (only axes + axis labels).
    At progress=1 the full curve + all markers are visible. Markers appear as
    the draw passes their x-position — a marker at x=1995 becomes visible the
    moment the curve reaches x=1995. The base bg is taken as-is; the data
    layer is re-drawn from scratch on a copy so the generator stays pure.
    """
    from PIL import ImageDraw

    from pipeline.composer.chart import _BODY_BOTTOM_FRAC, _HEADER_GAP
    from pipeline.composer.rich_slide import (
        _load_font,
    )

    img = base_bg.copy()
    pad_l = int(width * 0.10)
    pad_r = int(width * 0.07)
    body_top = max(top + _HEADER_GAP, int(height * 0.30))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    plot_w = width - pad_l - pad_r

    wipe = ImageDraw.Draw(img)
    # Wipe the full data + label-stack region (down from just below the header)
    # so the frame generator can re-draw at the requested progress without
    # leftover artifacts. Starts at ``top + 2`` (rather than ``body_top - 34``)
    # so a multi-row dodged callout stack from the base is fully cleared; header
    # content sits above ``top`` and is untouched.
    wipe.rectangle(
        [pad_l - 16, top + 2, pad_l + plot_w + pad_r + 8, body_bottom + 6],
        fill=palette["paper"],
    )

    data = visual["data"]
    points = data["points"]
    markers = data.get("markers") or []

    xs = [float(p["x"]) for p in points]
    ys = [float(p["y"]) for p in points]
    marker_xs = [float(m["x"]) for m in markers if isinstance(m, dict) and "x" in m]
    x_min = min(xs + marker_xs)
    x_max = max(xs + marker_xs)
    y_max = max(ys) or 1.0
    x_span = max(1.0, x_max - x_min)
    plot_h = body_bottom - body_top

    def _to_px(x: float, y: float) -> tuple[int, int]:
        px = pad_l + int(plot_w * (x - x_min) / x_span)
        py = body_top + int(plot_h * (1.0 - y / y_max))
        return px, py

    draw = ImageDraw.Draw(img)
    # Axes are always at full strength.
    draw.line([pad_l, body_bottom, pad_l + plot_w, body_bottom],
              fill=palette["muted"], width=2)
    draw.line([pad_l, body_top, pad_l, body_bottom],
              fill=palette["muted"], width=2)

    yf = _load_font("sans", "regular", 22)
    label_bb = draw.textbbox((0, 0), "9999", font=yf)
    label_h = label_bb[3] - label_bb[1]
    for x_label in (min(xs), max(xs)):
        s = f"{int(x_label)}"
        sb = draw.textbbox((0, 0), s, font=yf)
        px = pad_l + int(plot_w * (x_label - x_min) / x_span)
        draw.text((px - (sb[2] - sb[0]) // 2, body_bottom - label_h - 6),
                  s, font=yf, fill=palette["muted"])

    progress = max(0.0, min(1.0, progress))
    if progress > 0.0:
        px_points = [_to_px(p["x"], p["y"]) for p in points]
        seg_lengths = [
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            for a, b in zip(px_points, px_points[1:], strict=False)
        ]
        total = sum(seg_lengths) or 1.0
        target = total * progress
        consumed = 0.0
        cur_x_data = xs[0]
        finished = False
        for (a, b), seg_len, a_x_data, b_x_data in zip(
            list(zip(px_points, px_points[1:], strict=False)),
            seg_lengths,
            xs,
            xs[1:],
            strict=False,
        ):
            if consumed + seg_len <= target:
                draw.line([a, b], fill=palette["accent"], width=4)
                consumed += seg_len
                cur_x_data = b_x_data
            else:
                frac = (target - consumed) / seg_len if seg_len > 0 else 1.0
                end = (
                    a[0] + int((b[0] - a[0]) * frac),
                    a[1] + int((b[1] - a[1]) * frac),
                )
                draw.line([a, end], fill=palette["accent"], width=4)
                cur_x_data = a_x_data + (b_x_data - a_x_data) * frac
                finished = True
                break
        if not finished:
            cur_x_data = xs[-1]
        for (px, py), px_x in zip(px_points, xs, strict=False):
            if px_x <= cur_x_data + 1e-9:
                draw.ellipse([px - 5, py - 5, px + 5, py + 5],
                             fill=palette["accent"])
    else:
        cur_x_data = xs[0] - 1.0

    mf = _load_font("sans", "bold", 18)
    revealed = []
    for m in markers:
        mx = float(m["x"])
        if progress <= 1e-9:
            continue
        if mx > cur_x_data + 1e-9:
            continue  # the draw head has not reached this marker yet
        mpx = pad_l + int(plot_w * (mx - x_min) / x_span)
        draw.line([mpx, body_top + 8, mpx, body_bottom],
                  fill=palette["muted"], width=1)
        draw.ellipse([mpx - 7, body_top + 1, mpx + 7, body_top + 15],
                     fill=palette["ink"])
        revealed.append(Callout(x=mpx, label=str(m.get("label", ""))))

    placed = place_callouts(
        revealed,
        measure=lambda s: int(draw.textlength(s, font=mf)),
        left=pad_l, right=pad_l + plot_w, body_top=body_top, top_limit=top + 2,
    )
    _draw_placed_callouts(draw, placed, ink=palette["ink"], muted=palette["muted"],
                          font=mf, leader_from_y=body_top)

    return img


def _animate_bar_frame(
    progress: float,
    visual: dict[str, Any],
    base_bg: Any,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    top: int,
) -> Any:
    """Draw the `bar` chart with each bar grown to ``progress`` of its final width.

    Bars stagger-start: bar ``i`` (0-indexed) starts at ``i * BAR_STAGGER_FRAC``
    of the overall reveal and finishes at ``i * BAR_STAGGER_FRAC + grow_span``
    where ``grow_span = 1 - (n-1) * BAR_STAGGER_FRAC``. Labels render at full
    opacity from progress=0 so the chart never reads "broken". Value text
    appears once the bar has reached >= 90% of its final width.
    """
    from PIL import ImageDraw

    from pipeline.composer.chart import _BODY_BOTTOM_FRAC, _HEADER_GAP
    from pipeline.composer.rich_slide import (
        _load_font,
    )

    img = base_bg.copy()
    draw = ImageDraw.Draw(img)

    data = visual["data"]
    xs = data["x"]
    ys = [float(v) for v in data["y"]]
    unit = data.get("y_unit", "")
    pad = int(width * 0.07)

    label_f = _load_font("sans", "bold", 26)
    val_f = _load_font("serif", "bold", 28)
    max_v = max(ys) or 1.0
    track_w = int(width * 0.62)
    y0 = max(top + _HEADER_GAP, int(height * 0.28))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    row_h = int((body_bottom - y0) / len(xs))
    bar_h = min(int(row_h * 0.42), 46)

    n = len(xs)
    grow_span = max(0.0001, 1.0 - (n - 1) * BAR_STAGGER_FRAC)
    progress = max(0.0, min(1.0, progress))

    for i, (label, v) in enumerate(zip(xs, ys, strict=False)):
        start_frac = i * BAR_STAGGER_FRAC
        local = (progress - start_frac) / grow_span
        local = max(0.0, min(1.0, local))

        draw.text((pad, y0), str(label), font=label_f, fill=palette["ink"])
        by = y0 + 34
        full_bw = int(track_w * (v / max_v))
        bw = max(0, int(full_bw * local))
        if bw > 0:
            draw.rectangle([pad, by, pad + max(2, bw), by + bar_h],
                           fill=palette["accent"])
        if local >= 0.9:
            vtxt = f"{v:g}{unit}"
            draw.text((pad + max(2, full_bw) + 16, by + bar_h // 2 - 16),
                      vtxt, font=val_f, fill=palette["ink"])
        y0 += row_h

    return img


def _animate_stat_frame(
    progress: float,
    visual: dict[str, Any],
    base_bg: Any,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    top: int,
) -> Any:
    """Count the value digit-by-digit from 0 → final.

    For parseable values (e.g. ``"230,676"``, ``"$1.1B"``) digits are scaled by
    progress; surrounding characters (commas, currency markers, suffixes) are
    preserved verbatim. For values with no digit runs (e.g. ``"N/A"``) the
    final value is drawn at every frame with the accent color faded in from
    paper → accent by progress — so the chart never reads "broken".
    """
    from PIL import ImageDraw

    from pipeline.composer.chart import _HEADER_GAP
    from pipeline.composer.rich_slide import (
        _load_font,
    )

    img = base_bg.copy()
    draw = ImageDraw.Draw(img)

    data = visual["data"]
    final_value = str(data["value"])
    display_value, parsed_ok = _count_up_value(final_value, progress)

    if not parsed_ok:
        logger.warning(
            "chart_anim.stat_count_up_parse_failed",
            scene=visual.get("_scene_id", "?"),
            value=final_value,
        )

    cx = width // 2
    body_top = max(top + _HEADER_GAP, int(height * 0.30))

    num_f = _load_font("serif", "bold", 150)
    nb = draw.textbbox((0, 0), display_value, font=num_f)
    if parsed_ok:
        color = palette["accent"]
    else:
        # Fade-in fallback: blend paper → accent on the FINAL value by progress.
        a = palette["accent"]
        paper = palette["paper"]
        k = max(0.0, min(1.0, progress))
        color = (
            int(a[0] * k + paper[0] * (1 - k)),
            int(a[1] * k + paper[1] * (1 - k)),
            int(a[2] * k + paper[2] * (1 - k)),
        )
    draw.text((cx - (nb[2] - nb[0]) // 2, body_top), display_value,
              font=num_f, fill=color)
    y = body_top + nb[3] + 24

    unit = str(data.get("unit", ""))
    if unit:
        uf = _load_font("sans", "bold", 36)
        ub = draw.textbbox((0, 0), unit.upper(), font=uf)
        draw.text((cx - (ub[2] - ub[0]) // 2, y), unit.upper(),
                  font=uf, fill=palette["ink"])
        y += 52

    context = str(data.get("context", ""))
    if context:
        cf = _load_font("sans", "regular", 28)
        cb = draw.textbbox((0, 0), context, font=cf)
        draw.text((cx - (cb[2] - cb[0]) // 2, y), context,
                  font=cf, fill=palette["muted"])

    return img


# ── Orchestrator ───────────────────────────────────────────────────────────────
def _animated_dispatcher(chart_type: str):
    if chart_type == "line":
        return _animate_line_frame
    if chart_type == "bar":
        return _animate_bar_frame
    if chart_type == "stat_big_number":
        return _animate_stat_frame
    raise ValueError(
        f"chart_type {chart_type!r} has no animated variant in Sprint 2 "
        f"(supported: line, bar, stat_big_number)"
    )


def render_animated_chart(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict[str, Any] | None = None,
) -> Path:
    """Render an animated chart to ``{scene_id}_visual.mp4``.

    Mirrors ``composer/base.py:_camera_motion_to_video``: write a JPEG frame
    sequence to a tempdir, then run a single ffmpeg encode. The base background
    is built once via ``chart._build_background`` so the AI cache key is shared
    with the static path (no extra Flux call when the same scene was previously
    rendered static).

    Hold-tail optimization: the p=1.0 frame is rendered ONCE and re-used for
    every frame after the reveal so the orchestrator does not re-pay the
    drawing cost during the settle phase.
    """
    from PIL import ImageDraw

    from pipeline.composer.chart import (
        _build_background,
        _draw_header,
        _palette,
    )

    theme = theme or {}
    chart_type = visual["chart_type"]
    pal = _palette(theme)
    frame_fn = _animated_dispatcher(chart_type)
    easing = _resolve_easing(visual)
    reveal_sec = _resolve_reveal_duration(visual, duration_sec)

    total_frames = max(1, int(duration_sec * FPS))
    reveal_frames = max(1, int(reveal_sec * FPS))

    work_dir.mkdir(parents=True, exist_ok=True)
    bg = _build_background(visual, theme, width, height, work_dir, scene_id)
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, visual, width, height, pal)

    composite_png = work_dir / f"{scene_id}_chart.png"
    bg.save(composite_png)

    final_frame = frame_fn(1.0, visual, bg, width, height, pal, top)

    output = work_dir / f"{scene_id}_visual.mp4"
    pix_fmt = "yuv420p" if (width % 2 == 0 and height % 2 == 0) else "yuv444p"

    with tempfile.TemporaryDirectory(prefix=f"chart-anim-{scene_id}-") as tmp:
        frame_dir = Path(tmp)
        for idx in range(total_frames):
            if idx >= reveal_frames - 1:
                frame = final_frame
            else:
                t = idx / max(1, reveal_frames - 1)
                progress = easing(t)
                frame = frame_fn(progress, visual, bg, width, height, pal, top)
            frame.save(
                frame_dir / f"frame_{idx:05d}.jpg",
                quality=95,
                subsampling=0,
                optimize=False,
            )

        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(frame_dir / "frame_%05d.jpg"),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-pix_fmt",
                pix_fmt,
                "-r",
                str(FPS),
                str(output),
            ]
        )

    if not output.exists():
        raise RuntimeError(
            f"chart_anim {scene_id}: ffmpeg returned but {output} is missing"
        )
    logger.info(
        "chart_anim.rendered",
        scene=scene_id, chart_type=chart_type,
        duration_sec=duration_sec, reveal_sec=reveal_sec,
        frames=total_frames,
    )
    return output
