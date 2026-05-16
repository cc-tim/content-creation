"""pipeline mla — Multi-Language Audio tools.

`mla rebalance` retargets the secondary-locale narration (typically EN) to fit
within the MLA drift tolerance vs. the primary locale (typically zh-TW). It
asks Claude Haiku to rewrite only the offending scenes to a word budget
calibrated from each scene's observed TTS speech rate, then re-synthesizes
those scenes and verifies the gate. Iterates up to `--max-iterations`.

The command never touches the primary (zh-TW) narration or the compose stage —
it's intended to fix MLA drift in seconds, without a full re-render.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext
from pipeline.stages.tts import (
    _build_subtitle_entries,
    _concatenate_audio,
    _get_audio_duration_ms,
    compute_mla_tolerance_ms,
)
from pipeline.storyboard import Scene, Storyboard
from pipeline.utils.anthropic_key import get_anthropic_api_key
from pipeline.utils.srt import write_srt
from pipeline.voices.registry import VoiceRegistry

mla_app = typer.Typer(help="Multi-Language Audio (MLA) tools.")
_console = Console()


_REBALANCE_SYSTEM_PROMPT = """\
You rewrite English narration for educational documentary TTS to match a target
word budget. The English audio plays as an alternate track aligned with the
primary-locale (typically zh-TW) audio, so the rewritten English must read in
roughly the same wall-clock time as the primary.

Constraints:
- Preserve the exact meaning of the primary-locale reference. Names, numbers,
  dates, and quoted phrases must appear verbatim.
- Maintain documentary register: declarative, even pacing, no rhetorical flourish.
- Hit the target word count within ±2. Prefer fewer words to more.
- Output ONLY the rewritten English text, one scene per line, prefixed with the
  scene id and a single pipe character. No commentary, no blank lines.

OUTPUT FORMAT (one line per scene, no other text):
<scene_id>|<rewritten English>
"""


# Per-scene ratio above which we mark a scene as an overshoot offender.
PER_SCENE_OVER_RATIO = 1.15
# Per-scene ratio below which we mark a scene as an undershoot offender
# (only consequential if total drift exceeds tolerance).
PER_SCENE_UNDER_RATIO = 0.85


@dataclass
class _Offender:
    """One scene that needs rewriting."""

    scene_id: str
    primary_text: str
    primary_ms: int
    secondary_text: str
    secondary_ms: int
    secondary_words: int
    target_words: int
    direction: str  # "over" | "under"


# ── Word counting ────────────────────────────────────────────────────────────


_WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def count_english_words(text: str) -> int:
    """Count whitespace-bounded English tokens. Contractions count as one."""
    return len(_WORD_RE.findall(text))


def compute_target_words(
    *,
    current_secondary_words: int,
    current_secondary_ms: int,
    primary_ms: int,
    target_ratio: float,
    floor: int = 3,
) -> int:
    """Word budget calibrated from observed TTS speech rate.

    Scales current words by (target_ms / observed_ms), where target_ms is
    primary_ms × target_ratio (target_ratio < 1 leaves a safety margin so
    the new audio undershoots primary).
    """
    if current_secondary_ms <= 0 or current_secondary_words <= 0:
        # Can't calibrate — fall back to a coarse char-density estimate
        # (Mandarin ≈ 1.4× density per char vs English per word; primary text
        # length isn't available here, so just return the floor).
        return floor
    target_ms = primary_ms * target_ratio
    ratio = target_ms / current_secondary_ms
    return max(floor, round(current_secondary_words * ratio))


# ── Project loading ──────────────────────────────────────────────────────────


def _resolve_work_dir(work_dir: Path | None, project_id: int) -> Path:
    if work_dir is not None:
        return work_dir
    if project_id == 0:
        _console.print("[red]Provide --work-dir or --project-id[/red]")
        raise typer.Exit(1)
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_project(
    work_dir: Path,
) -> tuple[PipelineContext, Storyboard, Path]:
    context_path = work_dir / "context.json"
    if not context_path.exists():
        _console.print(f"[red]No context.json in {work_dir} — run produce first[/red]")
        raise typer.Exit(1)
    ctx = PipelineContext.load(context_path)
    if not ctx.storyboard_path or not ctx.storyboard_path.exists():
        _console.print("[red]No storyboard found on context[/red]")
        raise typer.Exit(1)
    storyboard = Storyboard.load(ctx.storyboard_path)
    audio_dir = work_dir / "audio"
    if not audio_dir.exists():
        _console.print(f"[red]No audio dir in {work_dir} — run TTS first[/red]")
        raise typer.Exit(1)
    return ctx, storyboard, audio_dir


# ── Observed durations ───────────────────────────────────────────────────────


def _observe_secondary_durations(
    scenes: list[Scene],
    sec_locale: str,
    audio_dir: Path,
) -> list[dict[str, Any]]:
    """Read durations of existing segment_<sec_locale>_NNN.mp3 files via ffprobe.

    Returns a list aligned to scenes, with shape compatible with the gate's
    `secondary_timings` arg: each entry has `duration_ms` and `skipped` set as
    appropriate.

    Raises if a scene has narration_alt[sec_locale] but no matching audio file —
    that means TTS hasn't been run since the alt text was added, and the
    observed timings would be lies.
    """
    timings: list[dict[str, Any]] = []
    missing: list[str] = []
    for i, scene in enumerate(scenes):
        text = scene.narration_alt.get(sec_locale, "")
        if not text:
            timings.append(
                {"index": i, "text": "", "duration_ms": 0, "skipped": True}
            )
            continue
        seg_path = audio_dir / f"segment_en_{i:03d}.mp3"
        if not seg_path.exists():
            missing.append(scene.id)
            timings.append(
                {"index": i, "text": text, "duration_ms": 0, "skipped": True}
            )
            continue
        duration_ms = _get_audio_duration_ms(seg_path)
        timings.append(
            {"index": i, "text": text, "duration_ms": duration_ms, "path": str(seg_path)}
        )
    if missing:
        _console.print(
            "[red]Missing secondary segment files for scenes: "
            f"{', '.join(missing)} — run `pipeline produce --start-from tts` "
            "to synthesize the new EN text first.[/red]"
        )
        raise typer.Exit(1)
    return timings


# ── Offender identification ──────────────────────────────────────────────────


def identify_offenders(
    *,
    scenes: list[Scene],
    primary_timings: list[dict[str, Any]],
    secondary_timings: list[dict[str, Any]],
    sec_locale: str,
    tolerance_ms: int,
    target_ratio: float,
) -> tuple[list[_Offender], int, int]:
    """Compute the offender list and totals.

    Total drift is computed over scenes where both primary and secondary
    contribute (skipped scenes on either side are excluded from totals).
    """
    total_primary_ms = 0
    total_secondary_ms = 0
    over_offenders: list[_Offender] = []
    under_candidates: list[_Offender] = []
    for i, scene in enumerate(scenes):
        if i >= len(primary_timings) or i >= len(secondary_timings):
            continue
        pri = primary_timings[i]
        sec = secondary_timings[i]
        if sec.get("skipped"):
            continue
        sec_text = scene.narration_alt.get(sec_locale, "") or str(sec.get("text") or "")
        if not sec_text:
            continue
        pri_ms = int(pri.get("duration_ms") or 0)
        sec_ms = int(sec.get("duration_ms") or 0)
        if pri_ms <= 0:
            continue
        total_primary_ms += pri_ms
        total_secondary_ms += sec_ms
        ratio = sec_ms / pri_ms
        sec_words = count_english_words(sec_text)
        if ratio > PER_SCENE_OVER_RATIO:
            target_words = compute_target_words(
                current_secondary_words=sec_words,
                current_secondary_ms=sec_ms,
                primary_ms=pri_ms,
                target_ratio=target_ratio,
            )
            over_offenders.append(_Offender(
                scene_id=scene.id,
                primary_text=scene.narration,
                primary_ms=pri_ms,
                secondary_text=sec_text,
                secondary_ms=sec_ms,
                secondary_words=sec_words,
                target_words=target_words,
                direction="over",
            ))
        elif ratio < PER_SCENE_UNDER_RATIO:
            # Aim back toward primary × target_ratio (typically 0.95, so a slight
            # undershoot is still fine — only expand when total drift forces it).
            target_words = compute_target_words(
                current_secondary_words=sec_words,
                current_secondary_ms=sec_ms,
                primary_ms=pri_ms,
                target_ratio=target_ratio,
            )
            under_candidates.append(_Offender(
                scene_id=scene.id,
                primary_text=scene.narration,
                primary_ms=pri_ms,
                secondary_text=sec_text,
                secondary_ms=sec_ms,
                secondary_words=sec_words,
                target_words=target_words,
                direction="under",
            ))

    total_drift = abs(total_secondary_ms - total_primary_ms)
    offenders: list[_Offender] = list(over_offenders)
    # Only enlist undershoots if total drift exceeds tolerance AND secondary < primary
    # (i.e. undershoot is the direction that's actually hurting).
    if total_drift > tolerance_ms and total_secondary_ms < total_primary_ms:
        offenders.extend(under_candidates)
    return offenders, total_primary_ms, total_secondary_ms


# ── Haiku rewrite ────────────────────────────────────────────────────────────


def _build_user_prompt(offenders: list[_Offender], primary_locale: str) -> str:
    lines = [f"Primary locale: {primary_locale}. Rewrite the following scenes:\n"]
    for o in offenders:
        direction_hint = (
            "expand to roughly the target word count while preserving meaning"
            if o.direction == "under"
            else "tighten to roughly the target word count by dropping articles, "
            "hedges, and redundant phrasing"
        )
        lines.append(
            f"[{o.scene_id}] {primary_locale} reference: {o.primary_text}\n"
            f"  current EN ({o.secondary_words} words, "
            f"{o.secondary_ms / 1000:.2f}s): {o.secondary_text}\n"
            f"  target words: {o.target_words}  ({direction_hint})\n"
        )
    return "\n".join(lines)


_RESPONSE_LINE_RE = re.compile(r"^(?P<id>[\w-]+)\|(?P<text>.+)$")


def parse_rewrite_response(raw: str) -> dict[str, str]:
    """Parse Haiku output into {scene_id: new_text}. Tolerates blank lines."""
    rewrites: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _RESPONSE_LINE_RE.match(line)
        if m:
            rewrites[m.group("id").strip()] = m.group("text").strip()
    return rewrites


def call_haiku_rewrite(
    offenders: list[_Offender],
    primary_locale: str,
    *,
    api_key: str | None = None,
) -> dict[str, str]:
    """Ask Claude Haiku to rewrite the offending scenes. Returns {scene_id: text}."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key or get_anthropic_api_key())
    user_prompt = _build_user_prompt(offenders, primary_locale)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=_REBALANCE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = msg.content[0].text.strip()
    return parse_rewrite_response(raw)


# ── Apply / re-synth ─────────────────────────────────────────────────────────


def _apply_rewrites(
    storyboard: Storyboard,
    rewrites: dict[str, str],
    sec_locale: str,
    storyboard_path: Path,
) -> int:
    """Write rewrites into storyboard.scenes[*].narration_alt[sec_locale]. Returns count."""
    applied = 0
    for scene in storyboard.scenes:
        if scene.id in rewrites:
            scene.narration_alt[sec_locale] = rewrites[scene.id]
            applied += 1
    if applied:
        storyboard.save(storyboard_path)
    return applied


async def _resynth_secondary_selective(
    ctx: PipelineContext,
    storyboard: Storyboard,
    audio_dir: Path,
    sec_locale: str,
    rewritten_scene_ids: set[str],
) -> list[dict[str, Any]]:
    """Re-synthesize only scenes whose IDs are in rewritten_scene_ids.

    For unchanged scenes the existing segment_en_NNN.mp3 is left alone and
    its duration is probed via ffprobe. This keeps unchanged-scene durations
    bit-identical across iterations — without this, every rebalance iteration
    re-rolls Fish-Audio non-determinism over all 30+ scenes and the gate can
    oscillate purely on engine noise (the exact failure mode this command is
    trying to fix).

    Re-concatenates the secondary narration mp3 and rebuilds the SRT against
    the updated text + durations.
    """
    config = PipelineConfig()
    registry = VoiceRegistry(config.VOICES_DIR)
    if ctx.secondary_voice_id:
        sec_engine, sec_profile = registry.resolve(ctx.secondary_voice_id)
    else:
        sec_engine, sec_profile = registry.default_for_locale(sec_locale)

    scenes = storyboard.scenes
    scene_pauses_ms = [int(s.pause_after_sec * 1000) for s in scenes]

    timings: list[dict[str, Any]] = []
    segment_paths: list[Path] = []
    cumulative_ms = 0

    for i, scene in enumerate(scenes):
        text = scene.narration_alt.get(sec_locale, "")
        if not text:
            timings.append({
                "index": i, "text": "", "path": None,
                "start_ms": cumulative_ms, "duration_ms": 0, "skipped": True,
            })
            if i < len(scene_pauses_ms):
                cumulative_ms += scene_pauses_ms[i]
            continue

        seg_path = audio_dir / f"segment_en_{i:03d}.mp3"
        if scene.id in rewritten_scene_ids or not seg_path.exists():
            # Synthesize fresh for changed scenes (or to fill a missing file).
            # Engines are sync and some (EdgeEngine) call asyncio.run internally,
            # which blows up inside this loop. Offload to a worker thread.
            await asyncio.to_thread(
                sec_engine.synthesize, text, seg_path, sec_profile, scene_id=scene.id,
            )

        duration_ms = _get_audio_duration_ms(seg_path)
        timings.append({
            "index": i, "text": text, "path": str(seg_path),
            "start_ms": cumulative_ms, "duration_ms": duration_ms,
        })
        segment_paths.append(seg_path)
        cumulative_ms += duration_ms
        if i < len(scene_pauses_ms):
            cumulative_ms += scene_pauses_ms[i]

    narration_path = audio_dir / f"narration_{sec_locale}.mp3"
    _concatenate_audio(segment_paths, narration_path)
    srt_entries = _build_subtitle_entries(
        [t for t in timings if not t.get("skipped")]
    )
    subtitle_path = audio_dir / f"subtitles_{sec_locale}.srt"
    write_srt(srt_entries, subtitle_path)

    ctx.secondary_narration_path = narration_path
    ctx.secondary_subtitle_path = subtitle_path
    ctx.save()
    return timings


# ── Reporting ────────────────────────────────────────────────────────────────


def _print_offender_table(offenders: list[_Offender], header: str) -> None:
    table = Table(box=box.ROUNDED, show_lines=False, title=header)
    table.add_column("Scene", style="cyan")
    table.add_column("Dir", style="yellow", width=4)
    table.add_column("Pri ms", justify="right")
    table.add_column("Sec ms", justify="right")
    table.add_column("Ratio", justify="right")
    table.add_column("Cur w", justify="right")
    table.add_column("Tgt w", justify="right")
    for o in offenders:
        ratio = o.secondary_ms / o.primary_ms if o.primary_ms else 0
        table.add_row(
            o.scene_id, o.direction, str(o.primary_ms), str(o.secondary_ms),
            f"{ratio:.2f}", str(o.secondary_words), str(o.target_words),
        )
    _console.print(table)


def _print_proposed_rewrites(
    offenders: list[_Offender], rewrites: dict[str, str]
) -> None:
    table = Table(box=box.ROUNDED, show_lines=True, title="Proposed rewrites")
    table.add_column("Scene", style="cyan")
    table.add_column("Tgt w", justify="right")
    table.add_column("New w", justify="right")
    table.add_column("Current EN", style="red", max_width=40)
    table.add_column("New EN", style="green", max_width=40)
    for o in offenders:
        new_text = rewrites.get(o.scene_id, "")
        new_words = count_english_words(new_text) if new_text else 0
        table.add_row(
            o.scene_id, str(o.target_words), str(new_words),
            o.secondary_text, new_text or "[dim](no rewrite)[/dim]",
        )
    _console.print(table)


def _estimate_projected_drift(
    offenders: list[_Offender],
    rewrites: dict[str, str],
    total_primary_ms: int,
    total_secondary_ms: int,
) -> tuple[int, int]:
    """Linear extrapolation: scale offending scene ms by new_words / current_words."""
    new_total_secondary_ms = total_secondary_ms
    rewritten_count = 0
    for o in offenders:
        new_text = rewrites.get(o.scene_id)
        if not new_text or o.secondary_words <= 0:
            continue
        new_words = count_english_words(new_text)
        scale = new_words / o.secondary_words
        delta_ms = int(o.secondary_ms * scale) - o.secondary_ms
        new_total_secondary_ms += delta_ms
        rewritten_count += 1
    projected_drift = abs(new_total_secondary_ms - total_primary_ms)
    return projected_drift, rewritten_count


# ── Async core ───────────────────────────────────────────────────────────────


async def _run_rebalance(  # noqa: PLR0915
    *,
    work_dir: Path,
    max_iterations: int,
    apply: bool,
    per_scene_target_ratio: float,
    secondary_locale: str | None,
) -> int:
    ctx, storyboard, audio_dir = _load_project(work_dir)
    sec_locale = secondary_locale or ctx.secondary_locale
    if not sec_locale:
        _console.print(
            "[red]No secondary locale on context and --secondary-locale not given[/red]"
        )
        return 1
    primary_timings = ctx.segment_timings or []
    if not primary_timings:
        _console.print("[red]ctx.segment_timings empty — run TTS first[/red]")
        return 1

    iteration = 1
    current_ratio = per_scene_target_ratio
    while True:
        sec_timings = _observe_secondary_durations(
            storyboard.scenes, sec_locale, audio_dir
        )
        # Compute total primary for tolerance — use only the scenes where the
        # secondary has audio (matches the gate's "skip empties" behavior).
        total_pri_for_tolerance = sum(
            int(p.get("duration_ms") or 0)
            for i, p in enumerate(primary_timings)
            if i < len(sec_timings) and not sec_timings[i].get("skipped")
        )
        tolerance_ms = compute_mla_tolerance_ms(
            total_pri_for_tolerance, ctx.mla_drift_tolerance_ms
        )

        # Patch offender scene text by referring to the live storyboard, not timings.
        for i, scene in enumerate(storyboard.scenes):
            if i < len(sec_timings) and not sec_timings[i].get("skipped"):
                sec_timings[i]["text"] = scene.narration_alt.get(sec_locale, "")

        offenders, total_primary_ms, total_secondary_ms = identify_offenders(
            scenes=storyboard.scenes,
            primary_timings=primary_timings,
            secondary_timings=sec_timings,
            sec_locale=sec_locale,
            tolerance_ms=tolerance_ms,
            target_ratio=current_ratio,
        )
        total_drift = abs(total_secondary_ms - total_primary_ms)
        _console.print(
            f"\n[bold]Iteration {iteration}/{max_iterations}[/bold]  "
            f"primary={total_primary_ms / 1000:.2f}s  "
            f"secondary={total_secondary_ms / 1000:.2f}s  "
            f"drift={total_drift / 1000:.2f}s  "
            f"tolerance=±{tolerance_ms / 1000:.2f}s  "
            f"target_ratio={current_ratio:.2f}"
        )

        if not offenders and total_drift <= tolerance_ms:
            _console.print("[green]✓ Already balanced — no rewrites needed.[/green]")
            return 0

        if not offenders and total_drift > tolerance_ms:
            _console.print(
                "[yellow]Total drift exceeds tolerance but no per-scene offenders "
                f"(±{PER_SCENE_OVER_RATIO}× / {PER_SCENE_UNDER_RATIO}×). The drift "
                "is spread across many in-range scenes — hand-edit needed.[/yellow]"
            )
            return 1

        _print_offender_table(offenders, f"Offenders (iteration {iteration})")

        with _console.status("Calling Claude Haiku..."):
            rewrites = call_haiku_rewrite(offenders, ctx.locale)

        if not rewrites:
            _console.print("[red]Haiku returned no parseable rewrites — aborting[/red]")
            return 1

        missing_rewrites = [o.scene_id for o in offenders if o.scene_id not in rewrites]
        if missing_rewrites:
            _console.print(
                f"[yellow]Warning: Haiku skipped {len(missing_rewrites)} offender(s): "
                f"{', '.join(missing_rewrites)}[/yellow]"
            )

        _print_proposed_rewrites(offenders, rewrites)

        projected_drift, rewritten = _estimate_projected_drift(
            offenders, rewrites, total_primary_ms, total_secondary_ms
        )
        _console.print(
            f"\n[dim]Projected total drift after rewrite: "
            f"{projected_drift / 1000:.2f}s (was {total_drift / 1000:.2f}s) "
            f"based on {rewritten} rewritten scene(s).[/dim]"
        )

        if not apply:
            _console.print(
                "\n[cyan]Dry run — re-run with [bold]--apply[/bold] to write "
                "rewrites and re-synthesize.[/cyan]"
            )
            return 0

        applied = _apply_rewrites(storyboard, rewrites, sec_locale, ctx.storyboard_path)
        _console.print(f"[green]Wrote {applied} rewrite(s) to storyboard.[/green]")

        rewritten_ids = set(rewrites.keys())
        with _console.status(
            f"Re-synthesizing {len(rewritten_ids)} changed scene(s) "
            f"(reusing existing audio for the rest)..."
        ):
            new_sec_timings = await _resynth_secondary_selective(
                ctx, storyboard, audio_dir, sec_locale, rewritten_ids
            )

        # Tighten ratio for the next iteration and loop.
        new_total_sec_ms = sum(
            int(t.get("duration_ms") or 0)
            for t in new_sec_timings
            if not t.get("skipped")
        )
        new_drift = abs(new_total_sec_ms - total_primary_ms)
        _console.print(
            f"[bold]Post-resynth:[/bold] secondary={new_total_sec_ms / 1000:.2f}s  "
            f"drift={new_drift / 1000:.2f}s  tolerance=±{tolerance_ms / 1000:.2f}s"
        )
        if new_drift <= tolerance_ms:
            _console.print("[green]✓ MLA gate now passes.[/green]")
            return 0

        if iteration >= max_iterations:
            _console.print(
                f"[red]Reached max iterations ({max_iterations}) and drift "
                f"({new_drift / 1000:.2f}s) still exceeds tolerance. "
                "Hand-edit the remaining offenders.[/red]"
            )
            return 1

        iteration += 1
        # Tighten margin for the next attempt: 0.95 → 0.90 → 0.85.
        current_ratio = max(0.80, current_ratio - 0.05)


# ── Typer command ────────────────────────────────────────────────────────────


@mla_app.command()
def rebalance(
    work_dir: Annotated[
        Path | None, typer.Option("--work-dir", help="Project directory")
    ] = None,
    project_id: Annotated[
        int, typer.Option("--project-id", help="Project ID")
    ] = 0,
    max_iterations: Annotated[
        int,
        typer.Option(
            "--max-iterations",
            help="Cap on Haiku→re-synth→check loop iterations.",
        ),
    ] = 3,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--no-apply",
            help="Apply rewrites and re-synthesize. Without it, dry-run only.",
        ),
    ] = False,
    per_scene_target_ratio: Annotated[
        float,
        typer.Option(
            "--per-scene-target-ratio",
            help="Aim for new secondary scenes to fit within this fraction of primary "
            "duration (0.95 = 5%% safety margin).",
        ),
    ] = 0.95,
    secondary_locale: Annotated[
        str | None,
        typer.Option(
            "--secondary-locale",
            help="Locale of narration_alt to rebalance. Defaults to ctx.secondary_locale.",
        ),
    ] = None,
) -> None:
    """Retarget secondary-locale narration to fit the MLA drift gate.

    Identifies scenes where the secondary (typically EN) TTS audio overshoots
    the primary by >15%, asks Claude Haiku to rewrite them to a word budget
    calibrated from each scene's observed speech rate, and (with --apply)
    re-synthesizes the secondary track. Iterates up to --max-iterations,
    tightening the safety margin each pass.
    """
    work_dir_resolved = _resolve_work_dir(work_dir, project_id)
    exit_code = asyncio.run(
        _run_rebalance(
            work_dir=work_dir_resolved,
            max_iterations=max_iterations,
            apply=apply,
            per_scene_target_ratio=per_scene_target_ratio,
            secondary_locale=secondary_locale,
        )
    )
    if exit_code:
        raise typer.Exit(exit_code)
