"""pipeline image-alignment — checks narration vs. existing image content.

Runs at the review gate, BEFORE TTS. For each scene that already has an image
on disk (article_image, image with visual.path, or a refit_path), asks a vision
model whether the narration accurately describes what the image shows. This
catches the class of errors that text-only proofread structurally cannot:
narration that claims a posture, object, time-of-day, or count that the actual
image contradicts (e.g., "sitting in a walker" when the medieval go-cart has
no seat and shows the child standing).

Generated_image scenes are skipped here — they have no image yet at this
point in the pipeline; post-compose visual_review catches those.

Usage:
    uv run pipeline image-alignment run --project-id <ID>
    uv run pipeline image-alignment run --project-id <ID> --apply
"""

from __future__ import annotations

import base64
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from pipeline.config import PipelineConfig
from pipeline.utils.anthropic_key import get_anthropic_api_key

image_alignment_app = typer.Typer(help="Pre-TTS narration↔image alignment check.")
_console = Console()


_SYSTEM_PROMPT = """\
You are a fact-checker for a YouTube video pipeline. You will see, for each
scene, an image and the narration that will be read over it. Your job: decide
whether the narration's specific claims about *what the image shows* are
consistent with the image.

What to flag:
1. POSTURE / ACTION mismatch — narration says "sitting", image shows standing;
   narration says "running", image shows still; etc.
2. OBJECT mismatch — narration names a chair, seat, door, weapon, vehicle, or
   any specific noun that does not appear in the image.
3. COUNT mismatch — narration says "three children", image shows one.
4. PERIOD / SETTING mismatch — narration says "Victorian parlor", image is
   clearly modern; narration says "night", image is daylit.
5. SUBJECT IDENTITY — narration says "infant Jesus" or "the suspect", image
   clearly shows a different category of subject.

What NOT to flag:
- Generic atmospheric narration that doesn't make image-specific claims.
- Narration about historical context that the image cannot prove or disprove
  (e.g., "this happened in 1440" — the year is metadata, not visual content).
- Stylistic differences (illustration vs. photo) — that's a style choice.

For each issue, write ONE line:
ISSUE|<scene_id>|MAJOR or MINOR|original phrase from narration|suggested fix|reason

- MAJOR: the narration says something the image clearly contradicts
- MINOR: ambiguous or partially supported
- "original phrase" must be a verbatim substring of the narration so it can be
  programmatically replaced. Keep it short (the offending phrase only).
- "suggested fix" must be a drop-in replacement that fits the same slot in the
  sentence and is consistent with the image.

CRITICAL LANGUAGE RULE: "suggested fix" MUST be written in the same language and
script as the narration. If the narration is in Traditional Chinese (zh-TW), the
suggested replacement must be Traditional Chinese — not English, not Simplified
Chinese, not romanization. If you cannot produce a same-language replacement,
omit the ISSUE line entirely rather than emitting a cross-language fix.

The suggested fix must be a phrase that grammatically replaces the original
in-place. Do NOT write commentary, descriptions of the image, or full sentence
rewrites in the suggested-fix slot. If a clean phrase-level replacement is not
possible, omit the ISSUE.

If every scene's narration is consistent with its image, output only: OK
"""




def _is_valid_image(p: Path) -> bool:
    """Cheap magic-byte check — PNG/JPEG only (no surprises)."""
    try:
        with p.open("rb") as f:
            head = f.read(8)
    except OSError:
        return False
    return head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")


def _resize_for_vision(src: Path, max_width: int = 640) -> Path:
    """Resize image to max_width px for cheaper vision API calls."""
    resized = src.parent / f"{src.stem}_alignsm{src.suffix}"
    if resized.exists():
        return resized
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
            "-vf", f"scale='min({max_width},iw)':-1", str(resized),
        ],
        check=False,
    )
    return resized if resized.exists() else src


def _collect_pretts_images(work_dir: Path) -> list[dict]:
    """Find scenes with images on disk at storyboard time (pre-TTS).

    Returns list of {scene_id, narration, section, image_path}. Skips scenes
    whose image hasn't been produced yet (generated_image without a render).
    """
    from pipeline.storyboard import Storyboard

    storyboard = Storyboard.load(work_dir / "storyboard.json")
    out: list[dict] = []
    for s in storyboard.scenes:
        v = s.visual or {}
        vtype = v.get("type", "")
        img_path: Path | None = None

        # article_image / image: pick refit_path if it exists, else path
        if vtype in ("article_image", "image"):
            refit = v.get("refit_path")
            path = v.get("path")
            cand = refit or path
            if cand:
                p = Path(cand)
                if not p.is_absolute():
                    # paths in storyboard are usually relative to repo root
                    p = Path.cwd() / p if not p.exists() else p
                if p.exists() and _is_valid_image(p):
                    img_path = p

        # generated_image: skip — image hasn't been rendered pre-TTS
        # still_frame / clip: source video frame — also skip for now

        if img_path is None:
            continue
        out.append(
            {
                "scene_id": s.id,
                "section": s.section,
                "narration": s.narration,
                "image_path": str(img_path),
            }
        )
    return out


def _build_review_content(items: list[dict]) -> list[dict]:
    """Build user-message content blocks: text preamble then per-scene image."""
    lines = ["Check each scene's narration against its image. List only mismatches.\n"]
    for i, it in enumerate(items, start=1):
        lines.append(
            f"--- SCENE {i}: {it['scene_id']} (section: {it['section']}) ---\n"
            f"NARRATION: {it['narration']}\n"
        )
    text_block = "\n".join(lines)

    content: list[dict] = [{"type": "text", "text": text_block}]
    for it in items:
        png = Path(it["image_path"])
        resized = _resize_for_vision(png)
        # Detect media type
        suffix = resized.suffix.lower().lstrip(".")
        media = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix or 'png'}"
        b64 = base64.standard_b64encode(resized.read_bytes()).decode()
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media, "data": b64},
            }
        )
        content.append({"type": "text", "text": f"^ scene {it['scene_id']}"})
    return content


def _parse_issues(raw: str) -> list[dict]:
    issues = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("ISSUE|"):
            continue
        parts = line.split("|", 5)
        if len(parts) == 6:
            _, scene_id, severity, original, suggested, reason = parts
            issues.append(
                {
                    "scene_id": scene_id.strip(),
                    "severity": severity.strip(),
                    "original": original.strip(),
                    "suggested": suggested.strip(),
                    "reason": reason.strip(),
                }
            )
    return issues


def check_alignment(work_dir: Path) -> list[dict]:
    """Run the vision pass. Returns issues (empty list when clean)."""
    import anthropic

    items = _collect_pretts_images(work_dir)
    if not items:
        return []

    client = anthropic.Anthropic(api_key=get_anthropic_api_key())
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_review_content(items)}],
    )
    raw = msg.content[0].text.strip()
    if raw == "OK":
        return []
    issues = _parse_issues(raw)
    if not issues:
        # Unstructured output — surface as a note rather than discard
        issues = [
            {
                "scene_id": "?",
                "severity": "MINOR",
                "original": "",
                "suggested": "",
                "reason": raw[:200],
            }
        ]
    return issues


def _has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


def _is_safe_swap(narration: str, original: str, suggested: str) -> bool:
    """Reject swaps that would inject a different language or rewrite the sentence.

    Even within the same language, an alignment "suggestion" that's much longer
    than the offending phrase tends to be a meaning-changing rewrite (e.g. the
    model substituted a description of the image for the narration's actual
    intent). Both classes have to be rejected.
    """
    if _has_cjk(narration) and not _has_cjk(suggested):
        return False
    return len(suggested) <= max(len(original) + 6, len(original) * 2)


def apply_alignment_fixes(work_dir: Path, issues: list[dict]) -> int:
    """Apply suggested fixes by substring-replacing in scene narration.

    Image-alignment fixes are NEVER applied non-interactively. Even with
    cross-language and length guards in place, suggestions can shift the
    scene's narrative purpose. This function exists for an explicit human
    invocation (`image-alignment run --apply`) and still gates each fix.
    """
    import json

    sb_path = work_dir / "storyboard.json"
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    applied = 0
    for iss in issues:
        if not iss["original"] or not iss["suggested"]:
            continue
        for s in data["scenes"]:
            if s["id"] != iss["scene_id"]:
                continue
            nar = s.get("narration", "")
            if iss["original"] not in nar:
                continue
            if not _is_safe_swap(nar, iss["original"], iss["suggested"]):
                continue
            s["narration"] = nar.replace(iss["original"], iss["suggested"])
            applied += 1
    sb_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


def print_alignment_table(issues: list[dict], console: Console | None = None) -> None:
    c = console or _console
    table = Table(box=box.ROUNDED, show_lines=True, title="Narration↔Image alignment")
    table.add_column("Scene", style="cyan", width=6)
    table.add_column("Sev", style="yellow", width=5)
    table.add_column("Narration phrase", style="red", max_width=30)
    table.add_column("Suggested", style="green", max_width=30)
    table.add_column("Reason", max_width=35)
    for iss in issues:
        table.add_row(
            iss["scene_id"], iss["severity"], iss["original"],
            iss["suggested"], iss["reason"],
        )
    c.print(table)


@image_alignment_app.command()
def run(
    work_dir: Annotated[Path | None, typer.Option("--work-dir", help="Project directory")] = None,
    project_id: Annotated[int, typer.Option("--project-id", help="Project ID")] = 0,
    apply: Annotated[bool, typer.Option("--apply/--no-apply", help="Auto-apply suggested fixes")] = False,
) -> None:
    """Check narration against existing scene images (pre-TTS)."""
    config = PipelineConfig()
    if work_dir is None:
        if project_id == 0:
            _console.print("[red]Provide --work-dir or --project-id[/red]")
            raise typer.Exit(1)
        work_dir = config.OUTPUT_DIR / "projects" / str(project_id)

    sb_path = work_dir / "storyboard.json"
    if not sb_path.exists():
        _console.print(f"[red]No storyboard.json in {work_dir}[/red]")
        raise typer.Exit(1)

    _console.print(f"[cyan]Image-alignment check[/cyan] {sb_path}")
    with _console.status("Calling Claude Haiku (vision)..."):
        issues = check_alignment(work_dir)

    if not issues:
        _console.print("[green]✓ Narration aligns with images.[/green]")
        return

    print_alignment_table(issues)

    if apply:
        n = apply_alignment_fixes(work_dir, issues)
        _console.print(f"\n[green]Applied {n}/{len(issues)} narration fix(es).[/green]")
        from pipeline.session_log import SessionEntry, append_session, new_session_id

        append_session(
            work_dir,
            SessionEntry(
                session_id=new_session_id(),
                timestamp=datetime.now().isoformat(timespec="seconds"),
                command="image-alignment run --apply",
                summary=f"image-alignment: applied {n}/{len(issues)} fixes",
            ),
        )
    else:
        _console.print(
            f"\n[dim]Found {len(issues)} alignment issue(s). "
            f"Re-run with [cyan]--apply[/cyan] to apply, "
            f"or edit storyboard manually.[/dim]"
        )
