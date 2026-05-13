from __future__ import annotations

import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from pipeline.utils.ffmpeg import run_ffmpeg


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class BookSceneSpec:
    """Shared geometry/material contract for book-framed scenes and page turns."""

    width: int
    height: int
    page: Rect
    inset: Rect
    bg: str = "#2b1f14"
    page_color: str = "#f4ead2"
    page_edge: str = "#caa766"
    shadow: str = "#1a120b"
    gutter: str = "#d9c299"

    @classmethod
    def open_book(cls, width: int, height: int) -> BookSceneSpec:
        margin_x = int(width * 0.065)
        margin_y = int(height * 0.075)
        page_x = margin_x
        page_y = margin_y
        page_w = width - margin_x * 2
        page_h = height - margin_y * 2
        inset_x = page_x + int(page_w * 0.075)
        inset_y = page_y + int(page_h * 0.105)
        inset_w = page_w - int(page_w * 0.15)
        inset_h = page_h - int(page_h * 0.21)
        return cls(
            width=width,
            height=height,
            page=Rect(page_x, page_y, page_w, page_h),
            inset=Rect(inset_x, inset_y, inset_w, inset_h),
        )

    def as_frame_geometry(self) -> dict[str, int | str]:
        return {
            "page_x": self.page.x,
            "page_y": self.page.y,
            "page_w": self.page.w,
            "page_h": self.page.h,
            "inset_x": self.inset.x,
            "inset_y": self.inset.y,
            "inset_w": self.inset.w,
            "inset_h": self.inset.h,
            "bg": self.bg,
            "page": self.page_color,
            "page_edge": self.page_edge,
            "shadow": self.shadow,
            "gutter": self.gutter,
        }


def render_book_page_turn_v2(
    *,
    frame_a: Path,
    frame_b: Path,
    out: Path,
    width: int,
    height: int,
    fps: int,
    duration_sec: float,
    page_count: int = 2,
    sfx: str | None = None,
) -> Path:
    spec = BookSceneSpec.open_book(width, height)
    total_frames = max(2, int(round(duration_sec * fps)))

    image_a = _fit_canvas(Image.open(frame_a).convert("RGBA"), width, height)
    image_b = _fit_canvas(Image.open(frame_b).convert("RGBA"), width, height)
    blank_page = _blank_book_canvas(spec)
    flip_count = max(1, min(8, int(page_count)))

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{out.stem}_frames_", dir=out.parent) as tmp:
        work = Path(tmp)
        for idx in range(total_frames):
            raw = idx / max(1, total_frames - 1)
            if flip_count <= 2:
                progress = _ease_in_out_cubic(raw)
                frame = _render_page_turn_frame(
                    image_a,
                    image_b,
                    spec=spec,
                    progress=progress,
                    raw_progress=raw,
                    page_count=flip_count,
                )
            else:
                scaled = min(raw * flip_count, flip_count - 0.0001)
                flip_idx = int(scaled)
                local_raw = scaled - flip_idx
                progress = _ease_in_out_cubic(local_raw)
                source = image_a if flip_idx == 0 else _early_destination_page(
                    blank_page,
                    image_b,
                    min(1.0, raw + 0.12),
                )
                under = image_b if flip_idx == flip_count - 1 else _early_destination_page(
                    blank_page,
                    image_b,
                    min(1.0, raw + 0.24),
                )
                frame = _render_page_turn_frame(
                    source,
                    under,
                    spec=spec,
                    progress=progress,
                    raw_progress=local_raw,
                    page_count=1,
                )
                _draw_page_stack_count(frame, spec, remaining=flip_count - flip_idx - 1)
            frame.convert("RGB").save(work / f"frame_{idx:05d}.png", optimize=False)

        _encode_frame_sequence(
            work / "frame_%05d.png",
            out,
            fps=fps,
            duration_sec=duration_sec,
            sfx=sfx,
        )
    return out


def _blank_book_canvas(spec: BookSceneSpec) -> Image.Image:
    page = spec.page
    inset = spec.inset
    canvas = Image.new("RGBA", (spec.width, spec.height), spec.bg)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle(
        (page.x + 16, page.y + 18, page.x + page.w + 16, page.y + page.h + 18),
        fill=(26, 18, 11, 148),
    )
    draw.rectangle(
        (page.x, page.y, page.x + page.w, page.y + page.h),
        fill=(244, 234, 210, 255),
        outline=(202, 167, 102, 255),
        width=5,
    )
    _draw_paper_grain(canvas, spec)
    _draw_calligraphy_texture(canvas, spec)
    _draw_soft_gutter(canvas, spec)
    for idx in range(7):
        x = page.x + 18 + idx * 5
        draw.line(
            [(x, page.y + 16), (x, page.y + page.h - 16)],
            fill=(163, 119, 64, max(18, 56 - idx * 6)),
            width=1,
        )
        xr = page.x + page.w - 18 - idx * 5
        draw.line(
            [(xr, page.y + 16), (xr, page.y + page.h - 16)],
            fill=(163, 119, 64, max(18, 56 - idx * 6)),
            width=1,
        )
    draw.rounded_rectangle(
        (inset.x - 4, inset.y - 4, inset.x + inset.w + 4, inset.y + inset.h + 4),
        radius=3,
        outline=(150, 115, 62, 42),
        width=2,
    )
    return canvas


def _draw_paper_grain(canvas: Image.Image, spec: BookSceneSpec) -> None:
    page = spec.page
    draw = ImageDraw.Draw(canvas, "RGBA")
    for idx in range(28):
        y = page.y + 18 + (idx * 37) % max(1, page.h - 36)
        alpha = 10 + idx % 13
        draw.line(
            [(page.x + 20, y), (page.x + page.w - 20, y + ((idx % 5) - 2))],
            fill=(150, 116, 68, alpha),
            width=1,
        )
    for idx in range(22):
        x = page.x + 24 + (idx * 53) % max(1, page.w - 48)
        alpha = 8 + idx % 9
        draw.line(
            [(x, page.y + 20), (x + ((idx % 7) - 3), page.y + page.h - 22)],
            fill=(255, 250, 226, alpha),
            width=1,
        )


def _draw_calligraphy_texture(canvas: Image.Image, spec: BookSceneSpec) -> None:
    page = spec.page
    gutter_x = page.x + page.w // 2
    draw = ImageDraw.Draw(canvas, "RGBA")
    regions = [
        (
            page.x + int(page.w * 0.11),
            page.y + int(page.h * 0.15),
            gutter_x - int(page.w * 0.055),
            page.y + int(page.h * 0.81),
        ),
        (
            gutter_x + int(page.w * 0.055),
            page.y + int(page.h * 0.15),
            page.x + page.w - int(page.w * 0.11),
            page.y + int(page.h * 0.81),
        ),
    ]
    for region_idx, (x0, y0, x1, y1) in enumerate(regions):
        col_gap = max(14, int(spec.width * 0.018))
        row_gap = max(16, int(spec.height * 0.028))
        for col_idx, x in enumerate(range(x0, x1, col_gap)):
            if col_idx % 5 == 4:
                continue
            for row_idx, y in enumerate(range(y0, y1, row_gap)):
                seed = (region_idx + 1) * 97 + col_idx * 17 + row_idx * 11
                length = max(9, int(col_gap * (0.50 + (seed % 5) * 0.08)))
                height = max(7, int(row_gap * (0.38 + (seed % 4) * 0.07)))
                alpha = 25 + seed % 32
                ink = (92, 62, 31, alpha)
                if seed % 3 == 0:
                    draw.arc((x, y, x + length, y + height), 200, 338, fill=ink, width=1)
                    draw.line(
                        [(x + length // 2, y + 2), (x + length // 2 - 4, y + height)],
                        fill=ink,
                        width=1,
                    )
                elif seed % 3 == 1:
                    draw.line([(x, y + height // 2), (x + length, y + 1)], fill=ink, width=1)
                    draw.line(
                        [(x + length // 3, y + 1), (x + length // 3 + 2, y + height)],
                        fill=ink,
                        width=1,
                    )
                    draw.arc((x + 2, y + 2, x + length, y + height + 2), 25, 140, fill=ink, width=1)
                else:
                    draw.line([(x + 2, y), (x + length - 1, y + height // 2)], fill=ink, width=1)
                    draw.line(
                        [(x + length - 2, y + height // 2), (x + 4, y + height)],
                        fill=ink,
                        width=1,
                    )
                if row_idx % 4 == 0:
                    draw.line(
                        [(x + length + 3, y + 3), (min(x1, x + length + col_gap // 2), y + 3)],
                        fill=(132, 92, 48, max(14, alpha - 18)),
                        width=1,
                    )


def _draw_soft_gutter(canvas: Image.Image, spec: BookSceneSpec) -> None:
    page = spec.page
    gutter_x = page.x + page.w // 2
    shadow = Image.new("RGBA", (spec.width, spec.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow, "RGBA")
    draw.line(
        [(gutter_x, page.y + 14), (gutter_x, page.y + page.h - 14)],
        fill=(129, 112, 76, 16),
        width=max(1, int(spec.width * 0.002)),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(5, int(spec.width * 0.010))))
    canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.line(
        [(gutter_x - 2, page.y + 18), (gutter_x - 2, page.y + page.h - 18)],
        fill=(255, 250, 228, 18),
        width=1,
    )
    draw.line(
        [(gutter_x + 2, page.y + 18), (gutter_x + 2, page.y + page.h - 18)],
        fill=(171, 143, 92, 12),
        width=1,
    )


def _early_destination_page(blank_page: Image.Image, image_b: Image.Image, raw_progress: float) -> Image.Image:
    reveal = min(1.0, max(0.0, (raw_progress - 0.22) / 0.58))
    if reveal <= 0:
        return blank_page
    eased = _ease_in_out_cubic(reveal)
    return Image.blend(blank_page, image_b, min(0.90, eased * 0.90))


def _draw_page_stack_count(canvas: Image.Image, spec: BookSceneSpec, *, remaining: int) -> None:
    if remaining <= 0:
        return
    page = spec.page
    draw = ImageDraw.Draw(canvas, "RGBA")
    visible = min(remaining, 5)
    for idx in range(visible):
        x = page.x + page.w - 10 - idx * 4
        alpha = 118 - idx * 16
        draw.line(
            [(x, page.y + 6 + idx), (x, page.y + page.h - 6 - idx)],
            fill=(255, 247, 222, alpha),
            width=2,
        )


def _render_page_turn_frame(
    image_a: Image.Image,
    image_b: Image.Image,
    *,
    spec: BookSceneSpec,
    progress: float,
    raw_progress: float,
    page_count: int,
) -> Image.Image:
    if progress <= 0.001:
        return image_a.copy()
    if progress >= 0.999:
        return image_b.copy()

    page = spec.page
    base = image_b.copy()
    outgoing_page = image_a.crop((page.x, page.y, page.x + page.w, page.y + page.h))

    flat_w = max(0, int(page.w * (1.0 - min(progress * 1.08, 1.0))))
    if flat_w > 2:
        flat = outgoing_page.crop((0, 0, flat_w, page.h))
        fade_alpha = int(255 * max(0.0, 1.0 - max(0.0, progress - 0.82) / 0.18))
        flat.putalpha(fade_alpha)
        base.alpha_composite(flat, (page.x, page.y))

    _draw_trailing_blank_sheets(base, spec, raw_progress, page_count)
    _draw_contact_shadow(base, spec, progress)

    sheet = _shade_turning_page(outgoing_page, progress)
    warped = _warp_page_to_canvas(sheet, spec, progress)
    blur_radius = 0.35 + math.sin(math.pi * progress) * 0.85
    if blur_radius > 0.45:
        warped = warped.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    base.alpha_composite(warped)
    _draw_page_edges(base, spec, progress)
    return base


def _draw_trailing_blank_sheets(
    canvas: Image.Image,
    spec: BookSceneSpec,
    raw_progress: float,
    page_count: int,
) -> None:
    if page_count <= 1:
        return
    page = spec.page
    draw = ImageDraw.Draw(canvas, "RGBA")
    for idx in range(1, page_count):
        offset = idx / (page_count + 1)
        local = min(1.0, max(0.0, raw_progress * 1.25 - offset * 0.35))
        if local <= 0.0 or local >= 1.0:
            continue
        curve = math.sin(math.pi * local)
        sheet_w = max(6, int(page.w * (0.018 + 0.035 * curve)))
        x = int(page.x + page.w * (1.0 - local) - sheet_w / 2)
        alpha = int(70 * curve)
        draw.rounded_rectangle(
            (x, page.y - 3, x + sheet_w, page.y + page.h + 3),
            radius=3,
            fill=(252, 241, 214, alpha),
            outline=(184, 154, 100, min(54, alpha + 10)),
            width=1,
        )


def _draw_contact_shadow(canvas: Image.Image, spec: BookSceneSpec, progress: float) -> None:
    page = spec.page
    curve = math.sin(math.pi * progress)
    if curve <= 0:
        return
    center_x = page.x + page.w * (1.0 - progress)
    sheet_w = page.w * (0.06 + 0.56 * curve)
    skew = page.w * 0.035 * curve * (1 if progress < 0.55 else -1)
    lift = page.h * 0.035 * curve
    quad = _sheet_quad(page, center_x, sheet_w, skew, lift)

    mask = Image.new("L", (spec.width, spec.height), 0)
    ImageDraw.Draw(mask).polygon(quad, fill=int(78 * curve))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(6, int(spec.width * 0.016))))
    shadow = Image.new("RGBA", (spec.width, spec.height), (42, 36, 28, 0))
    shadow.putalpha(mask)
    canvas.alpha_composite(shadow)


def _shade_turning_page(page_image: Image.Image, progress: float) -> Image.Image:
    page = page_image.copy()
    w, h = page.size
    curve = math.sin(math.pi * progress)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for x in range(w):
        nx = x / max(1, w - 1)
        edge_shadow = int(58 * curve * nx)
        back_tint = int(42 * curve * (1.0 - abs(nx - 0.58)))
        highlight = int(58 * curve * max(0.0, 1.0 - abs(nx - 0.32) / 0.13))
        if back_tint:
            draw.line((x, 0, x, h), fill=(245, 218, 166, back_tint))
        if edge_shadow:
            draw.line((x, 0, x, h), fill=(64, 55, 43, edge_shadow))
        if highlight:
            draw.line((x, 0, x, h), fill=(255, 250, 225, highlight))
    return Image.alpha_composite(page, overlay)


def _warp_page_to_canvas(
    page_image: Image.Image,
    spec: BookSceneSpec,
    progress: float,
) -> Image.Image:
    page = spec.page
    curve = math.sin(math.pi * progress)
    center_x = page.x + page.w * (1.0 - progress)
    sheet_w = page.w * (0.06 + 0.56 * curve)
    skew = page.w * 0.035 * curve * (1 if progress < 0.55 else -1)
    lift = page.h * 0.035 * curve
    quad = _sheet_quad(page, center_x, sheet_w, skew, lift)

    coeffs = _perspective_coeffs(
        quad,
        [(0, 0), (page.w, 0), (page.w, page.h), (0, page.h)],
    )
    return page_image.transform(
        (spec.width, spec.height),
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def _draw_page_edges(canvas: Image.Image, spec: BookSceneSpec, progress: float) -> None:
    page = spec.page
    curve = math.sin(math.pi * progress)
    if curve <= 0:
        return
    center_x = page.x + page.w * (1.0 - progress)
    sheet_w = page.w * (0.06 + 0.56 * curve)
    skew = page.w * 0.035 * curve * (1 if progress < 0.55 else -1)
    lift = page.h * 0.035 * curve
    quad = _sheet_quad(page, center_x, sheet_w, skew, lift)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.line([quad[0], quad[3]], fill=(255, 249, 229, int(145 * curve)), width=2)
    draw.line([quad[1], quad[2]], fill=(122, 99, 63, int(78 * curve)), width=2)


def _sheet_quad(
    page: Rect,
    center_x: float,
    sheet_w: float,
    skew: float,
    lift: float,
) -> list[tuple[float, float]]:
    left = center_x - sheet_w / 2
    right = center_x + sheet_w / 2
    return [
        (left + skew, page.y - lift),
        (right + skew * 0.25, page.y + lift * 0.22),
        (right - skew * 0.2, page.y + page.h - lift * 0.18),
        (left - skew, page.y + page.h + lift),
    ]


def _perspective_coeffs(
    output_points: list[tuple[float, float]],
    input_points: list[tuple[float, float]],
) -> tuple[float, ...]:
    matrix: list[list[float]] = []
    rhs: list[float] = []
    for (x, y), (u, v) in zip(output_points, input_points, strict=True):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rhs.append(u)
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.append(v)
    return tuple(_solve_linear_system(matrix, rhs))


def _solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(rhs)
    a = [row[:] + [rhs[idx]] for idx, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-9:
            raise ValueError("cannot solve perspective transform")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [value / scale for value in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            a[row] = [
                value - factor * a[col][idx]
                for idx, value in enumerate(a[row])
            ]
    return [a[row][-1] for row in range(n)]


def _fit_canvas(image: Image.Image, width: int, height: int) -> Image.Image:
    if image.size == (width, height):
        return image
    fitted = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    fitted.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
    return fitted


def _ease_in_out_cubic(value: float) -> float:
    if value < 0.5:
        return 4 * value * value * value
    return 1 - pow(-2 * value + 2, 3) / 2


def _encode_frame_sequence(
    pattern: Path,
    out: Path,
    *,
    fps: int,
    duration_sec: float,
    sfx: str | None,
) -> None:
    cmd: list[str] = [
        "ffmpeg", "-y",
        "-framerate", str(fps), "-i", str(pattern),
        "-f", "lavfi", "-t", str(duration_sec), "-i", "anullsrc=r=48000:cl=stereo",
    ]
    if sfx:
        cmd += ["-i", sfx]
        audio_filter = "[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
    else:
        audio_filter = "[1:a]anull[a]"
    cmd += [
        "-filter_complex", audio_filter,
        "-map", "0:v", "-map", "[a]",
        "-t", str(duration_sec),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
        "-shortest", str(out),
    ]
    run_ffmpeg(cmd)


def extract_video_frame(source: Path, out: Path, *, first: bool) -> Path:
    cmd = ["ffmpeg", "-y"]
    if not first:
        cmd += ["-sseof", "-0.5"]
    cmd += ["-i", str(source), "-frames:v", "1", "-update", "1", str(out)]
    run_ffmpeg(cmd)
    return out


def media_duration_sec(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0.01, float(result.stdout.strip()))
