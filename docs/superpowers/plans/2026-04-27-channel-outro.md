# Channel Outro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pre-rendered 20s channel outro that auto-attaches to every video at publish time, driven by a `pipeline outro build` CLI command and `outro_enabled` config flag per channel.

**Architecture:** Three changes in parallel: (1) extend `ChannelProfile` with `display_name`, `tagline`, and `outro_enabled` fields; (2) new `src/pipeline/outro/` package with an FFmpeg builder and Typer CLI; (3) `PublishStage.publish()` resolves profile before preflight so it can attach outro via concat-demux. Tests mock `subprocess.run` for builder tests; existing `run_ffmpeg` util handles execution.

**Tech Stack:** Python 3.11+, FFmpeg (subprocess), Typer, httpx (profile.png fetch), `src/pipeline/utils/ffmpeg.py` (`build_concat_cmd` + `run_ffmpeg`).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `configs/youtube_channels.toml` | Modify | Add `display_name`, `tagline`, `outro_enabled` to `ideal-parents-tw` |
| `src/pipeline/publish/channels.py` | Modify | Add 3 new fields to `ChannelProfile`; update `load_channel_config` loader |
| `src/pipeline/outro/__init__.py` | Create | Package marker |
| `src/pipeline/outro/builder.py` | Create | `build_outro(profile, output_path, aspect_ratio)` + `fetch_profile_png(profile, dest)` |
| `src/pipeline/outro/cli.py` | Create | `outro_app` Typer sub-app: `build`, `status` commands |
| `src/pipeline/publish/stage.py` | Modify | Move `resolve_profile` before `run_preflight`; add `_attach_outro` helper |
| `src/pipeline/cli.py` | Modify | Register `outro_app` under name `"outro"` |
| `tests/unit/publish/test_channels_outro.py` | Create | Load TOML with outro fields; assert `ChannelProfile.outro_enabled` etc. |
| `tests/unit/test_outro_builder.py` | Create | Mock `subprocess.run`; assert filter graph substrings + resolution per aspect ratio |
| `tests/unit/publish/test_publish_outro.py` | Create | `_attach_outro`: exists→concat called; missing+enabled→warning; enabled=false→skip |

---

### Task 1: Extend ChannelProfile with outro fields

**Files:**
- Modify: `src/pipeline/publish/channels.py`
- Modify: `configs/youtube_channels.toml`
- Create: `tests/unit/publish/test_channels_outro.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/publish/test_channels_outro.py
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipeline.publish.channels import load_channel_config


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "channels.toml"
    p.write_text(textwrap.dedent(content))
    return p


def test_outro_fields_loaded(tmp_path: Path) -> None:
    p = _write_toml(tmp_path, """
        [profiles.my-ch]
        niche = "parenting"
        locale = "zh-TW"
        channel_id = "UC123"
        voice_guide = ""
        default_tags = []
        category_id = 27
        display_name = "理想父母"
        tagline = "陪你走過每個育兒時刻"
        outro_enabled = true

        [routing]
        "parenting/zh-TW" = "my-ch"
    """)
    cfg = load_channel_config(p)
    prof = cfg.profiles["my-ch"]
    assert prof.display_name == "理想父母"
    assert prof.tagline == "陪你走過每個育兒時刻"
    assert prof.outro_enabled is True


def test_outro_fields_default_to_off(tmp_path: Path) -> None:
    p = _write_toml(tmp_path, """
        [profiles.bare]
        niche = "tech"
        locale = "en"
        channel_id = ""
        voice_guide = ""
        default_tags = []
        category_id = 28

        [routing]
        "tech/en" = "bare"
    """)
    cfg = load_channel_config(p)
    prof = cfg.profiles["bare"]
    assert prof.display_name == ""
    assert prof.tagline == ""
    assert prof.outro_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/publish/test_channels_outro.py -v
```
Expected: FAIL with `AttributeError: 'ChannelProfile' object has no attribute 'display_name'`

- [ ] **Step 3: Add fields to ChannelProfile and loader**

In `src/pipeline/publish/channels.py`, change `ChannelProfile` to:
```python
@dataclass(frozen=True)
class ChannelProfile:
    name: str
    niche: str
    locale: str
    channel_id: str
    voice_guide: str
    default_tags: list[str]
    category_id: int
    display_name: str = ""
    tagline: str = ""
    outro_enabled: bool = False
```

In `load_channel_config`, update the profile constructor:
```python
profiles[name] = ChannelProfile(
    name=name,
    niche=raw["niche"],
    locale=raw["locale"],
    channel_id=raw.get("channel_id", ""),
    voice_guide=raw.get("voice_guide", ""),
    default_tags=list(raw.get("default_tags", [])),
    category_id=int(raw["category_id"]),
    display_name=raw.get("display_name", ""),
    tagline=raw.get("tagline", ""),
    outro_enabled=bool(raw.get("outro_enabled", False)),
)
```

- [ ] **Step 4: Update configs/youtube_channels.toml**

Add three lines under `[profiles.ideal-parents-tw]`:
```toml
display_name = "理想父母"
tagline      = "陪你走過每個育兒時刻"
outro_enabled = true
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/unit/publish/test_channels_outro.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/publish/channels.py configs/youtube_channels.toml tests/unit/publish/test_channels_outro.py
git commit -m "feat(outro): extend ChannelProfile with display_name, tagline, outro_enabled"
```

---

### Task 2: outro package scaffold + builder unit tests

**Files:**
- Create: `src/pipeline/outro/__init__.py`
- Create: `src/pipeline/outro/builder.py` (signature + stub)
- Create: `tests/unit/test_outro_builder.py`

- [ ] **Step 1: Create package marker**

```python
# src/pipeline/outro/__init__.py
```
(empty file)

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/test_outro_builder.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from pipeline.outro.builder import build_outro
from pipeline.publish.channels import ChannelProfile


def _profile(outro_enabled: bool = True) -> ChannelProfile:
    return ChannelProfile(
        name="ideal-parents-tw",
        niche="parenting",
        locale="zh-TW",
        channel_id="UCOzL_agyMJLknQtXgLMIyyA",
        voice_guide="",
        default_tags=[],
        category_id=27,
        display_name="理想父母",
        tagline="陪你走過每個育兒時刻",
        outro_enabled=outro_enabled,
    )


def test_build_outro_calls_ffmpeg(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
            aspect_ratio="16:9",
        )

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"


def test_build_outro_landscape_resolution(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
            aspect_ratio="16:9",
        )

    cmd = mock_run.call_args[0][0]
    cmd_str = " ".join(cmd)
    assert "1920x1080" in cmd_str


def test_build_outro_portrait_resolution(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
            aspect_ratio="9:16",
        )

    cmd = mock_run.call_args[0][0]
    cmd_str = " ".join(cmd)
    assert "1080x1920" in cmd_str


def test_build_outro_contains_avatar_fade(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
        )

    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "fade=in" in cmd_str


def test_build_outro_contains_static_hold(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
        )

    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "tpad" in cmd_str
    assert "stop_mode=clone" in cmd_str


def test_build_outro_contains_channel_name(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
        )

    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "理想父母" in cmd_str
    assert "陪你走過每個育兒時刻" in cmd_str


def test_build_outro_contains_subscribe_text(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
        )

    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "訂閱頻道" in cmd_str


def test_build_outro_output_codec(tmp_path: Path) -> None:
    profile_png = tmp_path / "profile.png"
    profile_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    output = tmp_path / "outro.mp4"

    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=profile_png,
            output_path=output,
        )

    cmd = mock_run.call_args[0][0]
    assert "libx264" in cmd
    assert "aac" in cmd
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_outro_builder.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.outro.builder'`

- [ ] **Step 4: Write the builder stub**

```python
# src/pipeline/outro/builder.py
from __future__ import annotations

from pathlib import Path

from pipeline.publish.channels import ChannelProfile
from pipeline.utils.ffmpeg import run_ffmpeg


def build_outro(
    profile: ChannelProfile,
    profile_png_path: Path,
    output_path: Path,
    aspect_ratio: str = "16:9",
) -> None:
    """Render a 20s outro clip. Raises subprocess.CalledProcessError on FFmpeg failure."""
    raise NotImplementedError
```

- [ ] **Step 5: Verify tests still fail (but with NotImplementedError, not import error)**

```bash
uv run pytest tests/unit/test_outro_builder.py -v
```
Expected: FAIL with `NotImplementedError`

- [ ] **Step 6: Commit scaffold**

```bash
git add src/pipeline/outro/__init__.py src/pipeline/outro/builder.py tests/unit/test_outro_builder.py
git commit -m "test(outro): add builder unit tests + skeleton"
```

---

### Task 3: Implement build_outro filter graph

**Files:**
- Modify: `src/pipeline/outro/builder.py`

- [ ] **Step 1: Implement `build_outro` with full FFmpeg filter complex**

Replace the stub in `src/pipeline/outro/builder.py`:

```python
# src/pipeline/outro/builder.py
from __future__ import annotations

import textwrap
from pathlib import Path

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

    av = 200                          # avatar square size
    av_x = (w - av) // 2
    av_y = h // 5                     # upper fifth, visual center-top

    name_y = av_y + av + 20           # channel name baseline
    tag_y = name_y + 52               # tagline baseline
    pill_h = 50
    pill_w = 220
    pill_x = (w - pill_w) // 2
    pill_y = tag_y + 50               # subscribe pill top

    display = profile.display_name or profile.name
    tagline = profile.tagline

    # Build filter_complex as a single string. Use \\ to escape commas/colons inside
    # FFmpeg expression strings, and avoid shell interpolation issues by passing -filter_complex
    # as a single argument (no shell=True).
    fc = (
        # Background: amber vertical gradient via geq
        f"color=c=#fff8f0:s={w}x{h}:d=20[bg_raw];"
        f"[bg_raw]geq=r=255:g='248-20*(Y/{h})':b='240-44*(Y/{h})'[bg];"

        # Avatar: scale, circular alpha mask, fade in 0→1s
        f"[1:v]scale={av}:{av},format=rgba,"
        f"geq=lum='p(X\\,Y)':a='if(lt(sqrt(pow(X-{av//2}\\,2)+pow(Y-{av//2}\\,2)),{av//2}\\,255\\,0))'[av_circ];"
        f"[av_circ]fade=in:st=0:d=1[av_fade];"
        f"[bg][av_fade]overlay={av_x}:{av_y}[v1];"

        # Channel name: slides up 20px over 1–2.5s, fades in simultaneously
        f"[v1]drawtext=fontfile={_NOTO_BOLD}:"
        f"text='{display}':"
        f"fontcolor=#6b3f00:fontsize=42:"
        f"x=(w-text_w)/2:"
        f"y='if(between(t\\,1\\,2.5)\\,{name_y}+20-20*(t-1)/1.5\\,{name_y})':"
        f"alpha='if(lt(t\\,1)\\,0\\,if(between(t\\,1\\,2.5)\\,(t-1)/1.5\\,1))'[v2];"

        # Tagline: fades in over 2.5–4s
        f"[v2]drawtext=fontfile={_NOTO_REGULAR}:"
        f"text='{tagline}':"
        f"fontcolor=#a06030:fontsize=26:"
        f"x=(w-text_w)/2:y={tag_y}:"
        f"alpha='if(between(t\\,2.5\\,4)\\,(t-2.5)/1.5\\,if(gt(t\\,4)\\,1\\,0))'[v3];"

        # Subscribe pill: amber box + white text, fades in 4→6s, freezes 6→20s via tpad
        f"[v3]drawbox=x={pill_x}:y={pill_y}:w={pill_w}:h={pill_h}:"
        f"color=#f59e0b:t=fill:"
        f"enable='gte(t\\,4)',"
        f"drawtext=fontfile={_NOTO_BOLD}:"
        f"text='訂閱頻道 ▶':"
        f"fontcolor=white:fontsize=22:"
        f"x=(w-text_w)/2:y={pill_y + (pill_h - 22) // 2}:"
        f"enable='gte(t\\,4)'[v4];"

        # Static hold: clone last frame for 14s (total = 6s animated + 14s = 20s)
        f"[v4]tpad=stop_mode=clone:stop_duration=14[vout]"
    )

    # Music ident: 4 sine notes (C4=262Hz, E4=330Hz, G4=392Hz, C5=523Hz)
    # Each note is 0.8s, attack/decay 0.1s, starting at 0, 1, 2.5, 4s
    notes = [
        (262, 0.0),   # C4 at 0s
        (330, 1.0),   # E4 at 1s
        (392, 2.5),   # G4 at 2.5s
        (523, 4.0),   # C5 at 4s
    ]
    audio_inputs = []
    for i, (freq, start) in enumerate(notes):
        audio_inputs.extend([
            "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration=20",
        ])

    note_labels = "".join(f"[a{i}]" for i in range(len(notes)))
    aeq_parts = []
    for i, (freq, start) in enumerate(notes):
        aeq_parts.append(
            f"[{2 + i}:a]atrim=start={start}:end={start + 0.8},"
            f"asetpts=PTS-STARTPTS,"
            f"afade=in:st=0:d=0.1,afade=out:st=0.7:d=0.1,"
            f"adelay={int(start * 1000)}|{int(start * 1000)}[a{i}]"
        )
    audio_fc = (
        ";".join(aeq_parts)
        + f";{note_labels}amix=inputs={len(notes)}:normalize=0,"
        f"volume=-18dB,"
        f"afade=out:st=5.5:d=0.5,"
        f"apad=whole_dur=20[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=#fff8f0:s={w}x{h}:d=20",
        "-i", str(profile_png_path),
        *audio_inputs,
        "-filter_complex", fc + ";" + audio_fc,
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
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/unit/test_outro_builder.py -v
```
Expected: PASS (8 tests)

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/outro/builder.py
git commit -m "feat(outro): implement FFmpeg outro builder with amber gradient + animation"
```

---

### Task 4: fetch_profile_png helper

**Files:**
- Modify: `src/pipeline/outro/builder.py`
- Modify: `tests/unit/test_outro_builder.py`

- [ ] **Step 1: Add test for fetch_profile_png**

Append to `tests/unit/test_outro_builder.py`:

```python
from pipeline.outro.builder import fetch_profile_png


def test_fetch_profile_png_downloads_when_missing(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    channel_id = "UCOzL_agyMJLknQtXgLMIyyA"

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with patch("pipeline.outro.builder.httpx.get", return_value=fake_response) as mock_get:
        with patch("pipeline.outro.builder.httpx.get") as mock_get:
            mock_get.return_value = fake_response
            fetch_profile_png(channel_id=channel_id, dest=dest)

    assert dest.exists()
    assert dest.read_bytes() == fake_response.content


def test_fetch_profile_png_skips_when_exists(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    dest.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    with patch("pipeline.outro.builder.httpx.get") as mock_get:
        fetch_profile_png(channel_id="UC123", dest=dest)

    mock_get.assert_not_called()


def test_fetch_profile_png_raises_when_no_channel_id(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    with pytest.raises(ValueError, match="channel_id"):
        fetch_profile_png(channel_id="", dest=dest)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_outro_builder.py::test_fetch_profile_png_downloads_when_missing -v
```
Expected: FAIL with `ImportError` or `AttributeError`

- [ ] **Step 3: Implement fetch_profile_png**

Add to the top of `src/pipeline/outro/builder.py`:
```python
import os
import httpx
```

Add function after `build_outro`:

```python
def fetch_profile_png(channel_id: str, dest: Path) -> None:
    """Download channel profile image from YouTube Data API. Skip if dest already exists.

    Requires YOUTUBE_API_KEY env var. Raises ValueError if channel_id blank.
    """
    if dest.exists():
        return
    if not channel_id:
        raise ValueError(
            "channel_id is blank — set it in configs/youtube_channels.toml or "
            "drop profile.png manually at the expected path."
        )
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "YOUTUBE_API_KEY not set — cannot auto-fetch profile.png. "
            "Drop it manually at: " + str(dest)
        )
    url = (
        f"https://www.googleapis.com/youtube/v3/channels"
        f"?part=snippet&id={channel_id}&key={api_key}"
    )
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    if not items:
        raise RuntimeError(f"YouTube API returned no channel for id={channel_id}")
    thumb_url = items[0]["snippet"]["thumbnails"]["high"]["url"]
    img_resp = httpx.get(thumb_url, timeout=30)
    img_resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(img_resp.content)
```

- [ ] **Step 4: Fix the duplicate `patch` in test** (cleanup the test we just wrote)

Replace the `test_fetch_profile_png_downloads_when_missing` test with:

```python
def test_fetch_profile_png_downloads_when_missing(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    channel_id = "UCOzL_agyMJLknQtXgLMIyyA"

    api_resp = MagicMock()
    api_resp.status_code = 200
    api_resp.raise_for_status = MagicMock()
    api_resp.json.return_value = {
        "items": [{"snippet": {"thumbnails": {"high": {"url": "https://example.com/img.jpg"}}}}]
    }

    img_resp = MagicMock()
    img_resp.raise_for_status = MagicMock()
    img_resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with patch("pipeline.outro.builder.httpx.get", side_effect=[api_resp, img_resp]):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "fake-key"}):
            fetch_profile_png(channel_id=channel_id, dest=dest)

    assert dest.exists()
    assert dest.read_bytes() == img_resp.content
```

- [ ] **Step 5: Run all builder tests**

```bash
uv run pytest tests/unit/test_outro_builder.py -v
```
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/outro/builder.py tests/unit/test_outro_builder.py
git commit -m "feat(outro): add fetch_profile_png with YouTube API auto-download"
```

---

### Task 5: outro CLI (build + status)

**Files:**
- Create: `src/pipeline/outro/cli.py`
- Modify: `src/pipeline/cli.py`

- [ ] **Step 1: Create the CLI module**

```python
# src/pipeline/outro/cli.py
from __future__ import annotations

from pathlib import Path

import typer

outro_app = typer.Typer(help="Manage per-channel outro clips.")

_CHANNELS_DIR = Path("configs/channels")
_CHANNELS_TOML = Path("configs/youtube_channels.toml")


def _load_config():
    from pipeline.publish.channels import load_channel_config
    return load_channel_config(_CHANNELS_TOML)


@outro_app.command("build")
def build(
    profile: str = typer.Option(..., "--profile", help="Profile name from youtube_channels.toml"),
    aspect_ratio: str = typer.Option("16:9", "--aspect-ratio", help="16:9 or 9:16"),
    force: bool = typer.Option(False, "--force", help="Rebuild even if outro.mp4 already exists"),
) -> None:
    """Build (or rebuild) the outro clip for a channel profile."""
    cfg = _load_config()
    if profile not in cfg.profiles:
        typer.echo(f"Error: profile '{profile}' not in config.", err=True)
        raise typer.Exit(code=1)

    prof = cfg.profiles[profile]
    channel_dir = _CHANNELS_DIR / profile
    channel_dir.mkdir(parents=True, exist_ok=True)
    profile_png = channel_dir / "profile.png"
    output = channel_dir / "outro.mp4"

    if output.exists() and not force:
        typer.echo(f"outro.mp4 already exists at {output}. Pass --force to rebuild.")
        raise typer.Exit()

    if not profile_png.exists():
        typer.echo(f"profile.png not found at {profile_png} — fetching from YouTube API...")
        from pipeline.outro.builder import fetch_profile_png
        try:
            fetch_profile_png(channel_id=prof.channel_id, dest=profile_png)
            typer.echo(f"✓ Downloaded profile.png")
        except (ValueError, EnvironmentError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)

    typer.echo(f"Building outro for '{profile}' ({aspect_ratio})...")
    from pipeline.outro.builder import build_outro
    build_outro(profile=prof, profile_png_path=profile_png, output_path=output, aspect_ratio=aspect_ratio)
    typer.echo(f"✓ outro.mp4 written to {output}")


@outro_app.command("status")
def status() -> None:
    """Show outro build status across all configured profiles."""
    cfg = _load_config()
    for name, prof in sorted(cfg.profiles.items()):
        outro_path = _CHANNELS_DIR / name / "outro.mp4"
        enabled = "outro_enabled" if prof.outro_enabled else "disabled "
        built = "✓ built  " if outro_path.exists() else "✗ missing"
        size = f"{outro_path.stat().st_size // 1024}KB" if outro_path.exists() else ""
        typer.echo(f"{name:30s}  [{enabled}]  [{built}]  {size}")
```

- [ ] **Step 2: Register outro_app in cli.py**

In `src/pipeline/cli.py`, add the import:
```python
from pipeline.outro.cli import outro_app
```
And after the other `app.add_typer` lines:
```python
app.add_typer(outro_app, name="outro")
```

- [ ] **Step 3: Verify CLI is accessible**

```bash
uv run pipeline outro --help
```
Expected: Shows `build` and `status` subcommands without error.

```bash
uv run pipeline outro status
```
Expected: Shows `ideal-parents-tw` with `[outro_enabled]` and `[✗ missing]` (no outro built yet).

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/outro/cli.py src/pipeline/cli.py
git commit -m "feat(outro): add 'pipeline outro build/status' CLI commands"
```

---

### Task 6: ffmpeg_concat helper + PublishStage outro attachment

**Files:**
- Modify: `src/pipeline/utils/ffmpeg.py`
- Modify: `src/pipeline/publish/stage.py`
- Create: `tests/unit/publish/test_publish_outro.py`

- [ ] **Step 1: Add `ffmpeg_concat` to ffmpeg utils**

In `src/pipeline/utils/ffmpeg.py`, add after `run_ffmpeg`:

```python
def ffmpeg_concat(inputs: list[Path], output: Path) -> None:
    """Stream-copy concatenate multiple video files using the concat demuxer."""
    list_file = output.parent / f"_concat_{output.stem}.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in inputs),
        encoding="utf-8",
    )
    try:
        run_ffmpeg(build_concat_cmd(str(list_file), str(output)))
    finally:
        list_file.unlink(missing_ok=True)
```

- [ ] **Step 2: Write failing tests for publish outro attachment**

```python
# tests/unit/publish/test_publish_outro.py
from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.channels import ChannelConfig, ChannelProfile
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext


def _profile(outro_enabled: bool = True) -> ChannelProfile:
    return ChannelProfile(
        name="ideal-parents-tw",
        niche="parenting",
        locale="zh-TW",
        channel_id="UC123",
        voice_guide="",
        default_tags=[],
        category_id=27,
        display_name="理想父母",
        tagline="陪你走過每個育兒時刻",
        outro_enabled=outro_enabled,
    )


def _cfg(outro_enabled: bool = True) -> ChannelConfig:
    prof = _profile(outro_enabled)
    return ChannelConfig(
        profiles={"ideal-parents-tw": prof},
        routing={"parenting/zh-TW": "ideal-parents-tw"},
    )


def _stage(outro_enabled: bool = True) -> PublishStage:
    return PublishStage(
        client_factory=MagicMock(),
        channel_config=_cfg(outro_enabled),
    )


def _ctx(work_dir: Path) -> PipelineContext:
    video = work_dir / "final.mp4"
    video.write_bytes(b"x" * 1024)
    return PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=work_dir,
        niche="parenting",
        final_video_path=video,
    )


def test_outro_attached_when_enabled_and_exists(tmp_path: Path) -> None:
    """When outro_enabled=True and outro.mp4 exists, final_video_path is updated."""
    ctx = _ctx(tmp_path)
    outro_dir = tmp_path / "configs" / "channels" / "ideal-parents-tw"
    outro_dir.mkdir(parents=True)
    outro_mp4 = outro_dir / "outro.mp4"
    outro_mp4.write_bytes(b"x" * 512)

    merged = tmp_path / "compose" / "final_with_outro.mp4"

    with patch("pipeline.publish.stage.ffmpeg_concat") as mock_concat:
        # ffmpeg_concat writes the merged file (simulate)
        mock_concat.side_effect = lambda inputs, output: output.parent.mkdir(parents=True, exist_ok=True) or output.write_bytes(b"merged")

        stage = _stage(outro_enabled=True)
        stage._attach_outro(ctx, _profile(outro_enabled=True), channels_dir=outro_dir.parent.parent)

    mock_concat.assert_called_once()
    call_inputs, call_output = mock_concat.call_args[0]
    assert ctx.final_video_path.name == "final_with_outro.mp4"


def test_outro_skipped_when_disabled(tmp_path: Path) -> None:
    """When outro_enabled=False, final_video_path is not changed."""
    ctx = _ctx(tmp_path)
    original_path = ctx.final_video_path

    with patch("pipeline.publish.stage.ffmpeg_concat") as mock_concat:
        stage = _stage(outro_enabled=False)
        stage._attach_outro(ctx, _profile(outro_enabled=False), channels_dir=tmp_path)

    mock_concat.assert_not_called()
    assert ctx.final_video_path == original_path


def test_outro_warning_when_enabled_but_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When outro_enabled=True but outro.mp4 missing, logs warning and continues."""
    import logging
    ctx = _ctx(tmp_path)
    original_path = ctx.final_video_path

    with patch("pipeline.publish.stage.ffmpeg_concat") as mock_concat:
        stage = _stage(outro_enabled=True)
        with caplog.at_level(logging.WARNING):
            stage._attach_outro(ctx, _profile(outro_enabled=True), channels_dir=tmp_path / "configs" / "channels")

    mock_concat.assert_not_called()
    assert ctx.final_video_path == original_path
    assert any("outro" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/publish/test_publish_outro.py -v
```
Expected: FAIL with `AttributeError: 'PublishStage' object has no attribute '_attach_outro'`

- [ ] **Step 4: Implement `_attach_outro` and restructure `publish()`**

In `src/pipeline/publish/stage.py`:

1. Add import at the top:
```python
from pipeline.utils.ffmpeg import ffmpeg_concat
```

2. Add `_attach_outro` method to `PublishStage`:
```python
def _attach_outro(
    self,
    ctx: PipelineContext,
    profile: "ChannelProfile",
    channels_dir: Path | None = None,
) -> None:
    """Concat outro.mp4 onto ctx.final_video_path if outro_enabled. Non-blocking on missing file."""
    if not profile.outro_enabled:
        return
    base = channels_dir or Path("configs/channels")
    outro_path = base / profile.name / "outro.mp4"
    if not outro_path.exists():
        logger.warning("publish.outro_missing", expected=str(outro_path))
        return
    out = ctx.work_dir / "compose" / "final_with_outro.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_concat([ctx.final_video_path, outro_path], out)
    ctx.final_video_path = out
    ctx.save()
    logger.info("publish.outro_attached", outro=str(outro_path))
```

3. Restructure `publish()` to resolve profile before preflight:
```python
def publish(
    self,
    ctx: PipelineContext,
    *,
    profile_override: str | None,
) -> PipelineContext:
    """Run preflight + phased upload. Mutates and returns ctx."""
    from pipeline.notify.telegram import notify_failure
    from pipeline.publish.channels import resolve_profile

    # Resolve profile FIRST — needed for outro attachment before preflight validation
    profile = resolve_profile(
        self.channel_config,
        niche=ctx.niche,
        locale=ctx.locale,
        override=profile_override,
    )
    ctx.publish_profile = profile.name
    logger.info(
        "publish.profile_resolved",
        profile=profile.name,
        channel_id=profile.channel_id,
    )

    # Attach outro before preflight so preflight validates the merged file
    self._attach_outro(ctx, profile)

    run_preflight(ctx=ctx, privacy=self.privacy, schedule_iso=self.schedule_iso)

    metadata = load_metadata(ctx.work_dir / "metadata.json")
    upload_body = self._build_upload_body(metadata)

    if self.dry_run:
        import json as _json
        print(_json.dumps(upload_body, indent=2, ensure_ascii=False))
        return ctx

    client = self.client_factory(profile)

    try:
        self._phase_a_upload(client, ctx, upload_body)
        self._phase_b_thumbnail(client, ctx)
        self._phase_c_disclosure(client, ctx, metadata)
    except Exception as exc:
        notify_failure(
            project_id=ctx.project_id,
            profile=profile.name,
            phase=self._current_phase(ctx),
            error=str(exc),
            fix_command=f"pipeline publish {ctx.project_id}",
        )
        raise

    ctx.published_at = datetime.now(tz=timezone.utc).isoformat()
    ctx.save()
    return ctx
```

- [ ] **Step 5: Run all publish outro tests**

```bash
uv run pytest tests/unit/publish/test_publish_outro.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Run full unit test suite to check for regressions**

```bash
uv run pytest tests/unit/ -v --tb=short
```
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/utils/ffmpeg.py src/pipeline/publish/stage.py tests/unit/publish/test_publish_outro.py
git commit -m "feat(outro): attach outro in PublishStage.publish() before preflight"
```

---

### Task 7: create configs/channels directory and update CLAUDE.md triggers

**Files:**
- Create: `configs/channels/ideal-parents-tw/.gitkeep`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create directory with gitkeep**

```bash
mkdir -p configs/channels/ideal-parents-tw
touch configs/channels/ideal-parents-tw/.gitkeep
```

- [ ] **Step 2: Add NLP triggers to CLAUDE.md**

In `CLAUDE.md`, find the `## Commands` section and after the `publish and metadata workflow` block, add:

```markdown
## Outro workflow

```bash
# Build outro for a channel (fetches profile.png from YouTube API if missing)
uv run pipeline outro build --profile ideal-parents-tw

# Force rebuild (re-renders existing outro.mp4)
uv run pipeline outro build --profile ideal-parents-tw --force

# Check outro status across all profiles
uv run pipeline outro status
```

# Natural-language triggers (for the assistant):
#   "build the outro for X channel"         → pipeline outro build --profile X
#   "rebuild the outro"                      → pipeline outro build --profile X --force
#   "check outro status"                     → pipeline outro status
#   "why is outro not attaching?"            → pipeline outro status, check outro_enabled in TOML
```

- [ ] **Step 3: Commit**

```bash
git add configs/channels/ CLAUDE.md
git commit -m "chore(outro): add configs/channels dir + CLAUDE.md triggers for outro workflow"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/unit/ -v --tb=short
```
Expected: All tests pass.

- [ ] **Step 2: Verify CLI help**

```bash
uv run pipeline outro --help
uv run pipeline outro build --help
uv run pipeline outro status
```

- [ ] **Step 3: Verify publish stage restructure doesn't break existing publish tests**

```bash
uv run pytest tests/unit/publish/ -v --tb=short
```
Expected: All pass.

- [ ] **Step 4: Run ruff and mypy**

```bash
uv run ruff check src/pipeline/outro/ src/pipeline/publish/stage.py src/pipeline/utils/ffmpeg.py
uv run ruff format src/pipeline/outro/ src/pipeline/publish/stage.py src/pipeline/utils/ffmpeg.py
uv run mypy src/pipeline/outro/ src/pipeline/publish/stage.py
```
Fix any issues found.

- [ ] **Step 5: Final commit (lint fixes if any)**

```bash
git add -u
git commit -m "style(outro): ruff + mypy fixes"
```
