"""pipeline visual-review — frame extraction and automated visual QC.

Extracts representative frames from rendered scenes and optionally runs a
Claude Haiku vision pass to check image-narration fit and visual continuity.

Usage:
    uv run pipeline visual-review extract-frames --project-id <ID>
    uv run pipeline visual-review run --project-id <ID>
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from pipeline.config import PipelineConfig

visual_review_app = typer.Typer(help="Frame extraction and visual QC review.")
_console = Console()


def _extract_scene_frame(scene_mp4: Path, out_png: Path) -> bool:
    if not scene_mp4.exists():
        return False
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(scene_mp4),
        ],
        capture_output=True, text=True,
    )
    try:
        dur = float(proc.stdout.strip())
    except (ValueError, AttributeError):
        dur = 1.0
    midpoint = max(0.1, dur / 2)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{midpoint:.2f}",
            "-i", str(scene_mp4), "-frames:v", "1", "-q:v", "3", str(out_png),
        ],
        check=False,
    )
    return out_png.exists() and out_png.stat().st_size > 0


def extract_review_frames(work_dir: Path, clean: bool = True) -> list[dict]:
    """Extract one frame per scene from compose/scenes/<id>_final.mp4.

    Returns a list of {scene_id, narration, overlay_text, frame_path} dicts so
    the caller (the visual-review skill / assistant) can read and judge them.
    """
    from pipeline.storyboard import Storyboard

    storyboard = Storyboard.load(work_dir / "storyboard.json")
    scenes_dir = work_dir / "compose" / "scenes"
    frames_dir = scenes_dir / "_review_frames"
    if clean and frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    out: list[dict] = []
    for scene in storyboard.scenes:
        # Prefer with-overlay variant (matches what viewers see); fall back if absent.
        candidates = [
            scenes_dir / f"{scene.id}_final.mp4",
            scenes_dir / f"{scene.id}_final_no_overlay.mp4",
        ]
        scene_mp4 = next((p for p in candidates if p.exists()), None)
        if scene_mp4 is None:
            continue
        out_png = frames_dir / f"{scene.id}.png"
        if not _extract_scene_frame(scene_mp4, out_png):
            continue
        overlay_text = (scene.overlay or {}).get("text", "") if scene.overlay else ""
        out.append(
            {
                "scene_id": scene.id,
                "narration": scene.narration,
                "overlay_text": overlay_text,
                "frame_path": str(out_png),
            }
        )
    return out


# ── Automated visual QC (Claude Haiku vision pass) ──────────────────────

_REVIEW_SYSTEM_PROMPT = """\
You are a visual QC reviewer for a YouTube video pipeline. Your job: look at \
rendered frames and check whether each image fits its scene's narration and \
feels continuous with adjacent scenes.

For each frame you receive, you will also see:
- The scene's narration text (what the viewer hears)
- The scene's section (hook, context, rising, climax, aftermath, analysis)
- The visual prompt that was used to generate the image
- The narration of the previous and next scenes (for continuity check)

Checklist per scene:
1. IMAGE-NARRATION FIT — Does the image content match the narration?
   Mismatch examples: narration says "night" but image is daytime; narration
   describes "parent and child" but image shows a solo adult; narration talks
   about "crying" but character looks calm/smiling.
2. SEQUENCE CONTINUITY — Compare with the PREVIOUS frame. Do characters, \
settings,
   and lighting feel like the same visual world? Sudden changes in character
   appearance, setting, color palette, or art style = style drift.
3. SUBJECT OCCLUSION — Are faces, key props, or important areas covered by
   subtitle bands or overlay text boxes?

Severity:
- MAJOR: clear mismatch, style break, or occluded subject that hurts watchability
- MINOR: subtle inconsistency, minor palette shift, optional improvement

Output format (one line per issue, or OK):
ISSUE|<scene_id>|MAJOR or MINOR|observation|suggested fix|reason

If no issues across all frames, output only: OK"""


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PIPELINE_ANTHROPIC_API_KEY")
    if not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("PIPELINE_ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY. Set PIPELINE_ANTHROPIC_API_KEY in .env.")
    return key


def _resize_for_vision(png_path: Path, max_width: int = 640) -> Path:
    """Resize a PNG to *max_width* for cheaper vision API tokens. Returns resized path."""
    resized = png_path.parent / f"{png_path.stem}_sm.png"
    if resized.exists():
        return resized
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(png_path),
         "-vf", f"scale={max_width}:-1", str(resized)],
        check=False,
    )
    return resized if resized.exists() else png_path


def _build_review_content(
    frames: list[dict], storyboard_path: Path
) -> list[dict]:
    """Build the user message content blocks for Haiku's vision review.

    Returns a list of content blocks (text + images) for the API call.
    """
    from pipeline.storyboard import Storyboard

    sb = Storyboard.load(storyboard_path)
    scenes_by_id = {s.id: s for s in sb.scenes}

    # Build a text preamble with scene context
    lines = ["Review these rendered frames:\n"]
    for i, f in enumerate(frames):
        sid = f["scene_id"]
        scene = scenes_by_id.get(sid)
        section = scene.section if scene else "?"
        visual_prompt = ""
        if scene and scene.visual:
            visual_prompt = scene.visual.get("prompt", "")[:120]
        prev_nar = ""
        next_nar = ""
        if i > 0:
            prev_id = frames[i - 1]["scene_id"]
            prev_scene = scenes_by_id.get(prev_id)
            prev_nar = prev_scene.narration[:120] if prev_scene else ""
        if i < len(frames) - 1:
            next_id = frames[i + 1]["scene_id"]
            next_scene = scenes_by_id.get(next_id)
            next_nar = next_scene.narration[:120] if next_scene else ""

        lines.append(
            f"--- FRAME {i + 1}: {sid} (section: {section}) ---\n"
            f"NARRATION: {f['narration'][:200]}\n"
            f"VISUAL PROMPT: {visual_prompt}\n"
            f"OVERLAY: {f.get('overlay_text', '') or '(none)'}\n"
            f"PREV SCENE NAR: {prev_nar}\n"
            f"NEXT SCENE NAR: {next_nar}\n"
        )

    text_block = "\n".join(lines)

    # Build content blocks: text first, then images
    content: list[dict] = [{"type": "text", "text": text_block}]
    for f in frames:
        png = Path(f["frame_path"])
        resized = _resize_for_vision(png)
        img_bytes = resized.read_bytes()
        b64 = base64.standard_b64encode(img_bytes).decode()
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        })

    return content


def review_visual_fit(
    work_dir: Path,
    storyboard_path: Path | None = None,
) -> list[dict]:
    """Auto-review rendered frames for image-narration fit and visual continuity.

    Extracts frames if needed, then calls Claude Haiku with vision.
    Returns list of issue dicts (empty = clean).

    Issue dict format:
        {scene_id, severity, observation, suggestion, reason}
    """
    import anthropic

    sb_path = storyboard_path or (work_dir / "storyboard.json")
    if not sb_path.exists():
        return [{"scene_id": "?", "severity": "MAJOR",
                 "observation": "No storyboard found",
                 "suggestion": "Run produce first", "reason": "storyboard missing"}]

    # Extract frames (reuse existing if present)
    frames_dir = work_dir / "compose" / "scenes" / "_review_frames"
    if not frames_dir.exists() or not list(frames_dir.glob("*.png")):
        extract_review_frames(work_dir, clean=False)

    frames = []
    for png in sorted(frames_dir.glob("*.png")):
        if png.name.endswith("_sm.png"):
            continue
        sid = png.stem
        frames.append({"scene_id": sid, "frame_path": str(png)})

    if not frames:
        return [{"scene_id": "?", "severity": "MAJOR",
                 "observation": "No rendered frames found",
                 "suggestion": "Run compose rescene or reburn first",
                 "reason": "no frames"}]

    # Enrich with storyboard context
    from pipeline.storyboard import Storyboard
    sb = Storyboard.load(sb_path)
    scenes_by_id = {s.id: s for s in sb.scenes}
    for f in frames:
        scene = scenes_by_id.get(f["scene_id"])
        f["narration"] = scene.narration if scene else ""
        ovl = scene.overlay if scene else None
        f["overlay_text"] = (ovl or {}).get("text", "") if ovl else ""

    content = _build_review_content(frames, sb_path)

    client = anthropic.Anthropic(api_key=_get_api_key())
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=_REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    raw = msg.content[0].text.strip()
    if raw == "OK":
        return []

    issues = _parse_visual_issues(raw)
    if not issues:
        issues = [{"scene_id": "?", "severity": "NOTE", "observation": "",
                   "suggestion": "", "reason": raw[:200]}]
    return issues


def _parse_visual_issues(raw: str) -> list[dict]:
    issues = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("ISSUE|"):
            continue
        parts = line.split("|", 5)
        if len(parts) == 6:
            _, scene_id, severity, observation, suggestion, reason = parts
            issues.append({
                "scene_id": scene_id.strip(),
                "severity": severity.strip(),
                "observation": observation.strip(),
                "suggestion": suggestion.strip(),
                "reason": reason.strip(),
            })
    return issues


def print_visual_issues_table(
    issues: list[dict], console: Console | None = None
) -> None:
    """Print visual review issues as a Rich table."""
    c = console or _console
    if not issues:
        c.print("[green]  No visual issues found.[/green]")
        return

    table = Table(
        title="Visual Review Issues",
        box=box.SQUARE,
        title_style="bold magenta",
    )
    table.add_column("Scene", style="cyan", width=6)
    table.add_column("Sev", style="red", width=6)
    table.add_column("Observation", max_width=40)
    table.add_column("Suggestion", style="green", max_width=40)
    table.add_column("Reason", style="dim", max_width=30)

    for iss in issues:
        table.add_row(
            iss.get("scene_id", "?"),
            iss.get("severity", "?"),
            iss.get("observation", ""),
            iss.get("suggestion", ""),
            iss.get("reason", ""),
        )
    c.print(table)@visual_review_app.command("extract-frames")
def extract_frames_cmd(
    work_dir: Annotated[
        Path | None, typer.Option("--work-dir", help="Project directory")
    ] = None,
    project_id: Annotated[int, typer.Option("--project-id", help="Project ID")] = 0,
) -> None:
    """Extract a midpoint frame per rendered scene to compose/scenes/_review_frames/."""
    config = PipelineConfig()
    if work_dir is None:
        if project_id == 0:
            _console.print("[red]Provide --work-dir or --project-id[/red]")
            raise typer.Exit(1)
        work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    if not (work_dir / "storyboard.json").exists():
        _console.print(f"[red]No storyboard.json in {work_dir}[/red]")
        raise typer.Exit(1)

    rows = extract_review_frames(work_dir)
    if not rows:
        _console.print(
            "[yellow]No scene finals found. Run `compose rescene` or `compose reburn` first.[/yellow]"
        )
        raise typer.Exit(1)

    table = Table(title=f"Review frames @ {work_dir.name}")
    table.add_column("Scene", style="cyan", width=6)
    table.add_column("Narration (start)", max_width=50)
    table.add_column("Overlay", style="yellow", max_width=20)
    table.add_column("Frame")
    for r in rows:
        table.add_row(
            r["scene_id"],
            (r["narration"] or "")[:60],
            r["overlay_text"] or "(none)",
            r["frame_path"],
        )
    _console.print(table)
    _console.print(
        f"\n[green]Extracted {len(rows)} frames.[/green] "
        "The visual-review skill / a subagent can now Read these frames and report issues."
    )


@visual_review_app.command("run")
def run_visual_review_cmd(
    work_dir: Annotated[
        Path | None, typer.Option("--work-dir", help="Project directory")
    ] = None,
    project_id: Annotated[int, typer.Option("--project-id", help="Project ID")] = 0,
) -> None:
    """Run automated visual QC: check image-narration fit and continuity."""
    config = PipelineConfig()
    if work_dir is None:
        if project_id == 0:
            _console.print("[red]Provide --work-dir or --project-id[/red]")
            raise typer.Exit(1)
        work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    if not (work_dir / "storyboard.json").exists():
        _console.print(f"[red]No storyboard.json in {work_dir}[/red]")
        raise typer.Exit(1)

    _console.print("[bold]Running visual QC review (Claude Haiku)...[/bold]")
    issues = review_visual_fit(work_dir)
    print_visual_issues_table(issues)

    if issues:
        major = [i for i in issues if i.get("severity") == "MAJOR"]
        _console.print(
            f"\nFound {len(issues)} issue(s) ({len(major)} MAJOR). "
            "Fix by editing storyboard visual.prompt or overlay, then rescene."
        )
    else:
        _console.print("\n[green]No visual issues found.[/green]")
