from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from pipeline.config import PipelineConfig
from pipeline.publish.channels import ChannelProfile
from pipeline.utils.ffmpeg import run_ffmpeg

_NOTO_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_NOTO_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def _make_circle_png(src: Path, size: int, dest: Path) -> None:
    """Crop src image to a circle of given size and save as RGBA PNG."""
    img = Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    img.putalpha(mask)
    img.save(dest, "PNG")


def build_outro(
    profile: ChannelProfile,
    profile_png_path: Path,
    output_path: Path,
    aspect_ratio: str = "16:9",
    fps: int = 30,
    sample_rate: int = 48000,
) -> None:
    """Render a 20s outro clip. fps/sample_rate must match main video for concat compatibility."""
    if aspect_ratio == "9:16":
        w, h = 1080, 1920
    else:
        w, h = 1920, 1080

    av = 200                        # avatar square px
    av_x = (w - av) // 2
    av_y = h // 5                   # upper fifth

    name_y = av_y + av + 20         # channel name baseline
    tag_y = name_y + 52             # tagline baseline
    pill_h = 50
    pill_w = 220
    pill_x = (w - pill_w) // 2
    pill_y = tag_y + 54             # subscribe pill top

    display = profile.display_name or profile.name
    tagline = profile.tagline

    # Pre-process avatar into a circular RGBA PNG — more reliable than FFmpeg geq on packed RGBA
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _tmp:
        circle_png = Path(_tmp.name)
    _make_circle_png(profile_png_path, av, circle_png)

    # ------------------------------------------------------------------ #
    # Audio: 4-note C major arpeggio ident                                #
    # C4=262Hz E4=330Hz G4=392Hz C5=523Hz, starting at 0/1/2.5/4 s       #
    # ------------------------------------------------------------------ #
    notes = [
        (262, 0.0),
        (330, 1.0),
        (392, 2.5),
        (523, 4.0),
    ]
    # Each sine source is injected as a lavfi input (-f lavfi -i "sine=...")
    audio_input_args: list[str] = []
    for freq, _ in notes:
        audio_input_args.extend(["-f", "lavfi", "-i", f"sine=frequency={freq}:duration=20"])

    # Sine inputs start at index 1 (0=circle_png, 1..4=sines)
    audio_fc_parts = []
    for i, (_, start_s) in enumerate(notes):
        delay_ms = int(start_s * 1000)
        audio_fc_parts.append(
            f"[{1 + i}:a]"
            f"atrim=start={start_s}:end={start_s + 0.8},"
            f"asetpts=PTS-STARTPTS,"
            f"afade=in:st=0:d=0.1,"
            f"afade=out:st=0.7:d=0.1,"
            f"adelay={delay_ms}|{delay_ms}[a{i}]"
        )
    note_labels = "".join(f"[a{i}]" for i in range(len(notes)))
    audio_mix = (
        f"{note_labels}amix=inputs={len(notes)}:normalize=0,"
        f"volume=-18dB,"
        f"afade=out:st=5.5:d=0.5,"
        f"apad=whole_dur=20[aout]"
    )

    # ------------------------------------------------------------------ #
    # Video filter complex                                                 #
    # ------------------------------------------------------------------ #
    # Background: amber vertical gradient (#fff8f0 top → #ffe4c4 bottom)
    # format=rgb24 MUST come before geq so r/g/b params map to R/G/B planes, not Y/Cb/Cr
    bg = (
        f"color=c=#fff8f0:s={w}x{h}:d=20,format=rgb24[bg_flat];"
        f"[bg_flat]geq=r=255:g='248-20*(Y/{h})':b='240-44*(Y/{h})'[bg]"
    )

    # Avatar: Pillow-generated circular RGBA PNG is input 0; just fade it in
    avatar = (
        f"[0:v]fade=in:st=0:d=1[av_fade];"
        f"[bg][av_fade]overlay={av_x}:{av_y}[v1]"
    )

    # Channel name: slides up 20px over 1–2.5s + alpha fade
    name_text = display.replace("'", "\\'").replace(":", "\\:")
    name = (
        f"[v1]drawtext="
        f"fontfile={_NOTO_BOLD}:"
        f"text='{name_text}':"
        f"fontcolor=#6b3f00:"
        f"fontsize=42:"
        f"x=(w-text_w)/2:"
        f"y='if(between(t,1,2.5),{name_y}+20-20*(t-1)/1.5,{name_y})':"
        f"alpha='if(lt(t,1),0,if(between(t,1,2.5),(t-1)/1.5,1))'[v2]"
    )

    # Tagline: fades in over 2.5–4s
    tag_text = tagline.replace("'", "\\'").replace(":", "\\:")
    tagline_filter = (
        f"[v2]drawtext="
        f"fontfile={_NOTO_REGULAR}:"
        f"text='{tag_text}':"
        f"fontcolor=#a06030:"
        f"fontsize=26:"
        f"x=(w-text_w)/2:"
        f"y={tag_y}:"
        f"alpha='if(between(t,2.5,4),(t-2.5)/1.5,if(gt(t,4),1,0))'[v3]"
    )

    # Subscribe pill: amber rounded box + white text, enabled from t=4s
    pill = (
        f"[v3]"
        f"drawbox="
        f"x={pill_x}:y={pill_y}:w={pill_w}:h={pill_h}:"
        f"color=#f59e0b:t=fill:"
        f"enable='gte(t,4)',"
        f"drawtext="
        f"fontfile={_NOTO_BOLD}:"
        f"text='訂閱頻道 ▶':"
        f"fontcolor=white:"
        f"fontsize=22:"
        f"x=(w-text_w)/2:"
        f"y={pill_y + (pill_h - 22) // 2}:"
        f"enable='gte(t,4)'[v4]"
    )

    # Static hold: freeze last frame from 6s → 20s (14s padding)
    hold = "[v4]tpad=stop_mode=clone:stop_duration=14[vout]"

    video_fc = ";".join([bg, avatar, name, tagline_filter, pill, hold])
    audio_fc = ";".join(audio_fc_parts) + ";" + audio_mix
    filter_complex = video_fc + ";" + audio_fc

    cmd = [
        "ffmpeg", "-y",
        # Input 0: circular RGBA avatar PNG (Pillow pre-processed, looped as still image)
        "-loop", "1", "-i", str(circle_png),
        # Inputs 1+: sine audio sources
        *audio_input_args,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-ar", str(sample_rate),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-t", "20",
        str(output_path),
    ]
    try:
        run_ffmpeg(cmd)
    finally:
        circle_png.unlink(missing_ok=True)


def fetch_profile_png(channel_id: str, dest: Path) -> None:
    """Download channel profile image via YouTube Data API (API key) if dest doesn't exist.

    Reads PIPELINE_YOUTUBE_API_KEY from config/env. Raises ValueError if channel_id blank.
    Use the CLI `pipeline outro build` for automatic OAuth fallback.
    """
    if dest.exists():
        return
    if not channel_id:
        raise ValueError(
            "channel_id is blank in configs/youtube_channels.toml — "
            "either fill it in or drop profile.png manually at: " + str(dest)
        )
    api_key = PipelineConfig().YOUTUBE_API_KEY
    if not api_key:
        raise OSError(
            "PIPELINE_YOUTUBE_API_KEY not set — cannot auto-fetch profile.png. "
            "Drop it manually at: " + str(dest)
        )
    api_url = (
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=snippet&id={channel_id}&key={api_key}"
    )
    resp = httpx.get(api_url, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise RuntimeError(f"YouTube API returned no channel for id={channel_id}")
    thumb_url = items[0]["snippet"]["thumbnails"]["high"]["url"]
    img_resp = httpx.get(thumb_url, timeout=30)
    img_resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(img_resp.content)
