from __future__ import annotations

from pathlib import Path

import httpx

from pipeline.config import PipelineConfig
from pipeline.publish.channels import ChannelProfile
from pipeline.utils.ffmpeg import run_ffmpeg

_NOTO_BOLD = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
_NOTO_REGULAR = "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"


def build_outro(
    profile: ChannelProfile,
    profile_png_path: Path,
    output_path: Path,
    aspect_ratio: str = "16:9",
) -> None:
    """Render a 20s outro clip. Raises subprocess.CalledProcessError on FFmpeg failure."""
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

    # Number the sine inputs: they start at input index 2 (0=bg colour, 1=profile.png)
    audio_fc_parts = []
    for i, (_, start_s) in enumerate(notes):
        delay_ms = int(start_s * 1000)
        audio_fc_parts.append(
            f"[{2 + i}:a]"
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
    # Using geq with R=255, G=248→228, B=240→196
    bg = (
        f"color=c=#fff8f0:s={w}x{h}:d=20[bg_flat];"
        f"[bg_flat]geq=r=255:g='248-20*(Y/{h})':b='240-44*(Y/{h})'[bg]"
    )

    # Avatar: circular crop + fade in 0→1s
    av_r = av // 2
    avatar = (
        f"[1:v]scale={av}:{av},format=rgba,"
        f"geq="
        f"lum='p(X,Y)':"
        f"a='if(lt(sqrt(pow(X-{av_r},2)+pow(Y-{av_r},2)),{av_r}),255,0)'[av_circ];"
        f"[av_circ]fade=in:st=0:d=1[av_fade];"
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
        # Input 0: background colour source (used by geq)
        "-f", "lavfi", "-i", f"color=c=#fff8f0:s={w}x{h}:d=20",
        # Input 1: profile image
        "-i", str(profile_png_path),
        # Inputs 2+: sine audio sources
        *audio_input_args,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-t", "20",
        str(output_path),
    ]
    run_ffmpeg(cmd)


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
