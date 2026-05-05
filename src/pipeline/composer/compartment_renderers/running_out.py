from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


@dataclass
class CompartmentFrame:
    path: Path
    duration_sec: float


_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_face(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, kind: str) -> None:
    """Draw a simple PIL emoji-style face centered at (cx, cy)."""
    # Face circle
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(255, 220, 90),
        outline=(60, 40, 10),
        width=max(2, r // 20),
    )

    eye_y = cy - r // 3
    eye_dx = r // 2
    eye_r = max(3, r // 10)

    if kind == "neutral":
        draw.ellipse(
            (cx - eye_dx - eye_r, eye_y - eye_r, cx - eye_dx + eye_r, eye_y + eye_r),
            fill=(40, 20, 0),
        )
        draw.ellipse(
            (cx + eye_dx - eye_r, eye_y - eye_r, cx + eye_dx + eye_r, eye_y + eye_r),
            fill=(40, 20, 0),
        )
        draw.line(
            (cx - r // 2, cy + r // 3, cx + r // 2, cy + r // 3),
            fill=(40, 20, 0),
            width=max(2, r // 25),
        )
    elif kind == "worried":
        # Angled brows
        draw.line(
            (cx - eye_dx - r // 4, eye_y - r // 3, cx - eye_dx + r // 4, eye_y - r // 5),
            fill=(40, 20, 0),
            width=max(2, r // 20),
        )
        draw.line(
            (cx + eye_dx - r // 4, eye_y - r // 5, cx + eye_dx + r // 4, eye_y - r // 3),
            fill=(40, 20, 0),
            width=max(2, r // 20),
        )
        # Small eyes
        draw.ellipse(
            (cx - eye_dx - eye_r // 2, eye_y, cx - eye_dx + eye_r // 2, eye_y + eye_r),
            fill=(40, 20, 0),
        )
        draw.ellipse(
            (cx + eye_dx - eye_r // 2, eye_y, cx + eye_dx + eye_r // 2, eye_y + eye_r),
            fill=(40, 20, 0),
        )
        # Downturned mouth
        draw.arc(
            (cx - r // 2, cy + r // 6, cx + r // 2, cy + r // 2),
            start=180,
            end=360,
            fill=(40, 20, 0),
            width=max(2, r // 20),
        )
    elif kind == "panicked":
        # Wide round eyes
        draw.ellipse(
            (cx - eye_dx - eye_r, eye_y - eye_r - 2, cx - eye_dx + eye_r, eye_y + eye_r + 2),
            fill=(255, 255, 255),
            outline=(40, 20, 0),
            width=2,
        )
        draw.ellipse(
            (cx + eye_dx - eye_r, eye_y - eye_r - 2, cx + eye_dx + eye_r, eye_y + eye_r + 2),
            fill=(255, 255, 255),
            outline=(40, 20, 0),
            width=2,
        )
        draw.ellipse(
            (cx - eye_dx - 2, eye_y - 2, cx - eye_dx + 2, eye_y + 2),
            fill=(40, 20, 0),
        )
        draw.ellipse(
            (cx + eye_dx - 2, eye_y - 2, cx + eye_dx + 2, eye_y + 2),
            fill=(40, 20, 0),
        )
        # Open shout mouth
        draw.ellipse(
            (cx - r // 3, cy + r // 5, cx + r // 3, cy + r // 2 + r // 6),
            fill=(120, 20, 20),
            outline=(40, 0, 0),
            width=2,
        )
    else:
        # Unknown face: fall back to neutral
        _draw_face(draw, cx, cy, r, "neutral")


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        return (250, 200, 60)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def render_running_out_frames(
    out_dir: Path,
    config: dict,
    width: int,
    height: int,
) -> list[CompartmentFrame]:
    """Draw one PNG per stage and return the list in order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: Sequence[dict] = config.get("stages", [])
    duration = float(config.get("stage_duration_sec", 1.5))
    label = config.get("label", "")

    label_font = _load_font(max(20, height // 14))
    value_font = _load_font(max(48, height // 5))

    frames: list[CompartmentFrame] = []
    for idx, stage in enumerate(stages):
        img = Image.new("RGBA", (width, height), (15, 23, 42, 220))  # slate backdrop
        draw = ImageDraw.Draw(img)

        # Border accent in the stage color
        color = _parse_hex_color(stage.get("color", "#fbbf24"))
        draw.rectangle((0, 0, width - 1, height - 1), outline=color, width=6)

        # Label at top
        label_y = height // 12
        lw = draw.textlength(label, font=label_font)
        draw.text(
            ((width - lw) / 2, label_y),
            label,
            font=label_font,
            fill=(226, 232, 240, 255),
        )

        # Face in the middle
        face_cx = width // 2
        face_cy = int(height * 0.42)
        face_r = min(width, height) // 4
        _draw_face(draw, face_cx, face_cy, face_r, stage.get("face", "neutral"))

        # Big value at the bottom
        value = stage.get("value", "")
        vw = draw.textlength(value, font=value_font)
        draw.text(
            ((width - vw) / 2, int(height * 0.72)),
            value,
            font=value_font,
            fill=color + (255,),
        )

        frame_path = out_dir / f"running_out_{idx:02d}.png"
        img.save(frame_path)
        frames.append(CompartmentFrame(path=frame_path, duration_sec=duration))

    return frames
