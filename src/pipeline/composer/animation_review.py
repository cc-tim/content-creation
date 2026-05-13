from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from pipeline.composer.base import get_resolution
from pipeline.composer.transitions import BOOK_PAGE_STYLES, TransitionConfig, transition_cache_key
from pipeline.storyboard import Storyboard

ReviewKind = Literal["transition", "scene", "clip"]
ReviewStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class ReviewTarget:
    label: str
    path: Path
    kind: ReviewKind
    style: str = ""


@dataclass(frozen=True)
class FrameMetric:
    frame: int
    time_sec: float
    luma_mean: float
    dark_ratio: float
    edge_mean: float
    center_brown_score: float
    cover_gold_detail_ratio: float
    blank_like: bool
    brown_cover_like: bool


@dataclass(frozen=True)
class DeltaMetric:
    frame: int
    time_sec: float
    mean_abs_delta: float
    p95_abs_delta: float
    edge_delta: float


@dataclass(frozen=True)
class ReviewFinding:
    severity: ReviewStatus
    frame: int | None
    time_sec: float | None
    type: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "frame": self.frame,
            "time_sec": self.time_sec,
            "type": self.type,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ClipReview:
    label: str
    clip: str
    kind: ReviewKind
    duration_sec: float
    fps: float
    frame_count: int
    technical_status: ReviewStatus
    motion_status: ReviewStatus
    agent_review_status: ReviewStatus
    confidence: Literal["low", "medium", "high"]
    stats: dict[str, float | int]
    findings: list[ReviewFinding] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "clip": self.clip,
            "kind": self.kind,
            "duration_sec": self.duration_sec,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "technical_status": self.technical_status,
            "motion_status": self.motion_status,
            "agent_review_status": self.agent_review_status,
            "confidence": self.confidence,
            "stats": self.stats,
            "findings": [finding.to_dict() for finding in self.findings],
            "artifacts": self.artifacts,
        }


def review_project(
    project_root: Path,
    *,
    first: int = 4,
    include_scenes: bool = False,
    first_scenes: int = 3,
    out_dir: Path | None = None,
    variant: str = "no_overlay",
    max_samples: int = 18,
    scale_width: int = 320,
) -> list[ClipReview]:
    storyboard = Storyboard.load(project_root / "storyboard.json")
    targets = resolve_project_review_targets(
        project_root,
        storyboard,
        first=first,
        include_scenes=include_scenes,
        first_scenes=first_scenes,
        variant=variant,
    )
    output_root = out_dir or project_root / "compose" / "reviews" / "animation"
    return review_targets(
        targets,
        output_root,
        max_samples=max_samples,
        scale_width=scale_width,
    )


def review_targets(
    targets: list[ReviewTarget],
    out_dir: Path,
    *,
    max_samples: int = 18,
    scale_width: int = 320,
) -> list[ClipReview]:
    out_dir.mkdir(parents=True, exist_ok=True)
    reviews = [
        review_clip(
            target,
            out_dir,
            max_samples=max_samples,
            scale_width=scale_width,
        )
        for target in targets
    ]
    write_review_summary(reviews, out_dir)
    return reviews


def review_clip(
    target: ReviewTarget,
    out_root: Path,
    *,
    max_samples: int = 18,
    scale_width: int = 320,
) -> ClipReview:
    clip_dir = out_root / _safe_name(target.label)
    if clip_dir.exists():
        shutil.rmtree(clip_dir)
    clip_dir.mkdir(parents=True)

    probe = ffprobe(target.path)
    fps = _parse_rate(probe["streams"][0].get("avg_frame_rate", "30/1"))
    duration = float(probe["streams"][0].get("duration") or probe["format"].get("duration") or 0.0)

    with tempfile.TemporaryDirectory(prefix="animation-review-") as tmp:
        frames_dir = Path(tmp)
        _extract_scaled_frames(target.path, frames_dir, scale_width=scale_width)
        frames = sorted(frames_dir.glob("frame_*.png"))
        review = review_frame_files(
            target,
            frames,
            clip_dir,
            fps=fps,
            duration_sec=duration,
            max_samples=max_samples,
        )
    return review


def review_frame_files(
    target: ReviewTarget,
    frames: list[Path],
    out_dir: Path,
    *,
    fps: float,
    duration_sec: float,
    max_samples: int = 18,
) -> ClipReview:
    if len(frames) < 2:
        raise ValueError(f"need at least 2 frames to review {target.label}")

    frame_metrics, delta_metrics = compute_metrics(frames, fps=fps)
    stats = summarize_metrics(frame_metrics, delta_metrics)
    findings = build_findings(target, frame_metrics, delta_metrics, stats)
    sample_indices = evenly_spaced_indices(len(frames), max_samples)

    artifacts = {
        "frames_contact": str(out_dir / "frames_contact.jpg"),
        "diff_contact": str(out_dir / "diff_contact.jpg"),
        "motion_curve": str(out_dir / "motion_curve.jpg"),
        "motion_heatmap": str(out_dir / "motion_heatmap.jpg"),
        "metrics_json": str(out_dir / "metrics.json"),
    }
    build_frame_contact(
        frames,
        sample_indices,
        Path(artifacts["frames_contact"]),
        fps=fps,
        title=target.label,
    )
    build_diff_contact(
        frames,
        sample_indices,
        Path(artifacts["diff_contact"]),
        fps=fps,
        delta_metrics=delta_metrics,
        title=target.label,
    )
    build_motion_curve(delta_metrics, Path(artifacts["motion_curve"]), title=target.label)
    build_motion_heatmap(frames, Path(artifacts["motion_heatmap"]), title=target.label)

    technical_status = _status_for_findings(findings, category="technical")
    motion_status = _status_for_findings(findings, category="motion")
    agent_status = "fail" if "fail" in {technical_status, motion_status} else (
        "warn" if "warn" in {technical_status, motion_status} else "pass"
    )
    review = ClipReview(
        label=target.label,
        clip=str(target.path),
        kind=target.kind,
        duration_sec=duration_sec,
        fps=fps,
        frame_count=len(frames),
        technical_status=technical_status,
        motion_status=motion_status,
        agent_review_status=agent_status,
        confidence="high" if len(frames) >= 12 else "medium",
        stats=stats,
        findings=findings,
        artifacts=artifacts,
    )
    Path(artifacts["metrics_json"]).write_text(
        json.dumps(review.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return review


def resolve_project_review_targets(
    project_root: Path,
    storyboard: Storyboard,
    *,
    first: int = 4,
    include_scenes: bool = False,
    first_scenes: int = 3,
    variant: str = "no_overlay",
) -> list[ReviewTarget]:
    targets: list[ReviewTarget] = []
    if first > 0:
        intro = _resolve_intro_transition_clip(project_root, storyboard, variant=variant)
        if intro is not None:
            targets.append(intro)
        for transition in storyboard.transitions:
            if len([t for t in targets if t.kind == "transition"]) >= first:
                break
            if transition.style == "none" or transition.duration_sec <= 0:
                continue
            clip = _resolve_transition_clip(project_root, storyboard, transition, variant=variant)
            if clip is not None:
                targets.append(clip)

    if include_scenes:
        for scene in storyboard.scenes[: max(0, first_scenes)]:
            clip = _resolve_scene_clip(project_root, storyboard, scene.id, variant=variant)
            if clip is not None:
                targets.append(clip)
    return targets


def ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,duration,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(result.stdout)


def compute_metrics(frames: list[Path], *, fps: float) -> tuple[list[FrameMetric], list[DeltaMetric]]:
    frame_metrics: list[FrameMetric] = []
    delta_metrics: list[DeltaMetric] = []
    prev_gray: Image.Image | None = None
    prev_edge: Image.Image | None = None
    for idx, frame in enumerate(frames):
        image = Image.open(frame).convert("RGB")
        gray = ImageOps.grayscale(image)
        edge = gray.filter(ImageFilter.FIND_EDGES)
        frame_metrics.append(_frame_metric(idx, idx / fps, image, gray, edge))
        if prev_gray is not None and prev_edge is not None:
            diff = ImageChops.difference(gray, prev_gray)
            edge_diff = ImageChops.difference(edge, prev_edge)
            delta_metrics.append(
                DeltaMetric(
                    frame=idx - 1,
                    time_sec=(idx - 1) / fps,
                    mean_abs_delta=_mean_luma(diff),
                    p95_abs_delta=_hist_percentile(diff, 0.95),
                    edge_delta=_mean_luma(edge_diff),
                )
            )
        prev_gray = gray
        prev_edge = edge
    return frame_metrics, delta_metrics


def summarize_metrics(
    frame_metrics: list[FrameMetric],
    delta_metrics: list[DeltaMetric],
) -> dict[str, float | int]:
    deltas = [m.mean_abs_delta for m in delta_metrics]
    edge_deltas = [m.edge_delta for m in delta_metrics]
    if not deltas:
        return {}
    median_delta = statistics.median(deltas)
    mad_delta = statistics.median([abs(value - median_delta) for value in deltas])
    spike_threshold = max(median_delta + 3.0 * mad_delta, median_delta * 1.85, 8.0)
    freeze_threshold = max(0.18, median_delta * 0.08)
    derivative = [abs(deltas[idx] - deltas[idx - 1]) for idx in range(1, len(deltas))]
    if derivative:
        median_derivative = statistics.median(derivative)
        mad_derivative = statistics.median([abs(value - median_derivative) for value in derivative])
    else:
        median_derivative = 0.0
        mad_derivative = 0.0
    jerk_threshold = max(median_derivative + 4.0 * mad_derivative, median_derivative * 2.5, 4.0)
    blank_frames = [m for m in frame_metrics if m.blank_like]
    center_column_frames = [
        m for m in frame_metrics
        if m.center_brown_score > 13.0 and not m.brown_cover_like
    ]
    brown_cover_frames = [m for m in frame_metrics if m.brown_cover_like]
    return {
        "delta_min": min(deltas),
        "delta_median": median_delta,
        "delta_mean": sum(deltas) / len(deltas),
        "delta_max": max(deltas),
        "p95_delta_max": max(m.p95_abs_delta for m in delta_metrics),
        "edge_delta_mean": sum(edge_deltas) / len(edge_deltas),
        "edge_delta_max": max(edge_deltas),
        "spike_threshold": spike_threshold,
        "spike_count": sum(1 for value in deltas if value > spike_threshold),
        "freeze_threshold": freeze_threshold,
        "freeze_pair_count": sum(1 for value in deltas if value < freeze_threshold),
        "jerk_threshold": jerk_threshold,
        "jerk_count": sum(1 for value in derivative if value > jerk_threshold),
        "dark_frame_count": sum(1 for m in frame_metrics if m.dark_ratio > 0.85),
        "dark_ratio_max": max(m.dark_ratio for m in frame_metrics),
        "luma_min": min(m.luma_mean for m in frame_metrics),
        "luma_max": max(m.luma_mean for m in frame_metrics),
        "blank_like_frame_count": len(blank_frames),
        "blank_like_ratio": len(blank_frames) / len(frame_metrics),
        "center_brown_column_frame_count": len(center_column_frames),
        "center_brown_column_ratio": len(center_column_frames) / len(frame_metrics),
        "center_brown_score_max": max(m.center_brown_score for m in frame_metrics),
        "brown_cover_like_frame_count": len(brown_cover_frames),
        "brown_cover_like_ratio": len(brown_cover_frames) / len(frame_metrics),
        "distinct_motion_bins": _distinct_motion_bins(deltas),
    }


def build_findings(
    target: ReviewTarget,
    frame_metrics: list[FrameMetric],
    delta_metrics: list[DeltaMetric],
    stats: dict[str, float | int],
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    dark_frame_count = int(stats.get("dark_frame_count", 0))
    if dark_frame_count:
        first = next(m for m in frame_metrics if m.dark_ratio > 0.85)
        findings.append(ReviewFinding(
            "fail",
            first.frame,
            first.time_sec,
            "black_or_near_black_frame",
            f"{dark_frame_count} frame(s) are black or near-black.",
            "Inspect render inputs and concat boundaries before judging animation quality.",
        ))

    if target.kind == "scene":
        freeze_pairs = int(stats.get("freeze_pair_count", 0))
        if freeze_pairs / max(1, len(delta_metrics)) > 0.45:
            findings.append(ReviewFinding(
                "warn",
                None,
                None,
                "static_scene_hold",
                "Scene is mostly static; this may be intentional, but it is weak for an animation requirement.",
                "Add controlled pan/zoom, parallax, page-surface drift, or another explicit scene-motion primitive.",
            ))

    if target.kind == "transition":
        spike_count = int(stats.get("spike_count", 0))
        if spike_count > 3:
            first_spike = _first_delta_above(delta_metrics, float(stats["spike_threshold"]))
            findings.append(ReviewFinding(
                "warn",
                first_spike.frame if first_spike else None,
                first_spike.time_sec if first_spike else None,
                "repeated_motion_spikes",
                f"{spike_count} abrupt visual-delta spike(s) detected during the transition.",
                "Retune easing/page timing, add motion blur, or reduce the number of fast page pulses.",
            ))
        elif spike_count:
            first_spike = _first_delta_above(delta_metrics, float(stats["spike_threshold"]))
            findings.append(ReviewFinding(
                "warn",
                first_spike.frame if first_spike else None,
                first_spike.time_sec if first_spike else None,
                "motion_spike",
                "A large visual-delta spike may read as a pop.",
                "Inspect the diff sheet around the flagged frame.",
            ))

        blank_ratio = float(stats.get("blank_like_ratio", 0.0))
        if blank_ratio > 0.32:
            blank = next((m for m in frame_metrics if m.blank_like), None)
            findings.append(ReviewFinding(
                "warn",
                blank.frame if blank else None,
                blank.time_sec if blank else None,
                "blank_page_dominance",
                "Blank or low-detail book pages dominate a substantial part of the transition.",
                "Fill blank pages with low-contrast ancient text/calligraphy texture so the flip reads intentional and premium.",
            ))

        center_ratio = float(stats.get("center_brown_column_ratio", 0.0))
        if center_ratio > 0.30:
            center = max(frame_metrics, key=lambda m: m.center_brown_score)
            findings.append(ReviewFinding(
                "warn",
                center.frame,
                center.time_sec,
                "center_brown_column_artifact",
                "A brown vertical center/gutter column is visually prominent during the transition.",
                "Narrow or soften the gutter, match it to paper tone, or hide it with page texture/shadow continuity.",
            ))

        late_cutoff = len(delta_metrics) * 0.80
        late_spikes = [
            m for idx, m in enumerate(delta_metrics)
            if idx >= late_cutoff and m.mean_abs_delta > float(stats["spike_threshold"])
        ]
        if late_spikes:
            spike = late_spikes[0]
            findings.append(ReviewFinding(
                "warn",
                spike.frame,
                spike.time_sec,
                "late_reveal_pulse",
                "The destination scene reveal has a late high-energy pulse.",
                "Reveal the next scene earlier under the page, or extend the transition so the reveal does not feel like a pop.",
            ))

    if target.label == "intro":
        early_frames = frame_metrics[: max(3, len(frame_metrics) // 5)]
        cover_ratio = (
            sum(1 for m in early_frames if m.brown_cover_like) / max(1, len(early_frames))
        )
        title_detail = max((m.edge_mean for m in early_frames), default=0.0)
        gold_detail = max((m.cover_gold_detail_ratio for m in early_frames), default=0.0)
        if cover_ratio > 0.55 and title_detail < 18.0 and gold_detail < 0.001:
            findings.append(ReviewFinding(
                "warn",
                early_frames[0].frame if early_frames else None,
                early_frames[0].time_sec if early_frames else None,
                "intro_empty_brown_cover",
                "Intro begins on an empty brown cover with little title/detail energy.",
                "Add a shiny gold title treatment or embossed emblem so the opening frame earns attention before the page turn.",
            ))

    return findings


def write_review_summary(reviews: list[ClipReview], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps([review.to_dict() for review in reviews], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(_render_markdown(reviews), encoding="utf-8")


def build_frame_contact(
    frames: list[Path],
    indices: list[int],
    out: Path,
    *,
    fps: float,
    title: str,
) -> None:
    thumbs = []
    for idx in indices:
        img = Image.open(frames[idx]).convert("RGB")
        thumbs.append(_label_image(img, f"f{idx}  {idx / fps:.2f}s"))
    _save_grid(thumbs, out, title=f"{title} sampled frames")


def build_diff_contact(
    frames: list[Path],
    indices: list[int],
    out: Path,
    *,
    fps: float,
    delta_metrics: list[DeltaMetric],
    title: str,
) -> None:
    thumbs = []
    for idx in indices:
        idx2 = min(len(frames) - 1, idx + 1)
        a = Image.open(frames[idx]).convert("L")
        b = Image.open(frames[idx2]).convert("L")
        diff = ImageOps.autocontrast(ImageChops.difference(a, b).convert("RGB"), cutoff=1)
        delta = delta_metrics[idx].mean_abs_delta if idx < len(delta_metrics) else 0.0
        thumbs.append(_label_image(diff, f"f{idx}->{idx2} d={delta:.1f}"))
    _save_grid(thumbs, out, title=f"{title} consecutive-frame diff")


def build_motion_curve(delta_metrics: list[DeltaMetric], out: Path, *, title: str) -> None:
    values = [m.mean_abs_delta for m in delta_metrics]
    edge_values = [m.edge_delta for m in delta_metrics]
    w, h = 1100, 430
    left, top, right, bottom = 70, 54, 1040, 335
    canvas = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 18), f"{title} motion curve", fill=(20, 20, 20))
    draw.rectangle((left, top, right, bottom), outline=(180, 180, 180))
    if values:
        maxv = max(values + edge_values + [1.0])
        _draw_series(draw, values, (left, top, right, bottom), maxv, fill=(32, 90, 190))
        _draw_series(draw, edge_values, (left, top, right, bottom), maxv, fill=(190, 70, 40))
        median_value = statistics.median(values)
        y = bottom - (median_value / maxv) * (bottom - top)
        draw.line((left, y, right, y), fill=(80, 80, 80), width=1)
        draw.text((left, bottom + 18), "blue=mean luma delta, red=edge delta, gray=median", fill=(30, 30, 30))
        draw.text((left, bottom + 46), f"frames={len(values)+1} median_delta={median_value:.2f} max_delta={max(values):.2f}", fill=(30, 30, 30))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)


def build_motion_heatmap(frames: list[Path], out: Path, *, title: str) -> None:
    accum: Image.Image | None = None
    prev: Image.Image | None = None
    for frame in frames:
        gray = Image.open(frame).convert("L")
        if prev is not None:
            diff = ImageChops.difference(gray, prev)
            accum = diff if accum is None else ImageChops.lighter(accum, diff)
        prev = gray
    if accum is None:
        return
    heat = ImageOps.autocontrast(accum)
    heat = ImageOps.colorize(heat, black="#101010", white="#ffef5a", mid="#c72929")
    heat = _label_image(heat.convert("RGB"), f"{title} accumulated motion heatmap")
    out.parent.mkdir(parents=True, exist_ok=True)
    heat.save(out, quality=92)


def evenly_spaced_indices(count: int, max_samples: int) -> list[int]:
    if count <= max_samples:
        return list(range(count))
    return sorted({round(i * (count - 1) / (max_samples - 1)) for i in range(max_samples)})


def _resolve_transition_clip(
    project_root: Path,
    storyboard: Storyboard,
    transition: Any,
    *,
    variant: str,
) -> ReviewTarget | None:
    scene_a = _resolve_scene_clip(project_root, storyboard, transition.from_scene, variant=variant)
    scene_b = _resolve_scene_clip(project_root, storyboard, transition.to_scene, variant=variant)
    if scene_a is None or scene_b is None:
        return None
    try:
        cfg = TransitionConfig.from_transition(transition)
    except ValueError:
        return None
    key = transition_cache_key(scene_a.path, scene_b.path, cfg)
    clip = project_root / "compose" / "transitions" / f"{key}.mp4"
    if not clip.exists():
        return None
    return ReviewTarget(
        f"{transition.from_scene}_{transition.to_scene}",
        clip,
        "transition",
        style=transition.style,
    )


def _resolve_intro_transition_clip(
    project_root: Path,
    storyboard: Storyboard,
    *,
    variant: str,
) -> ReviewTarget | None:
    style = storyboard.theme.intro_transition_style or ""
    if not style or not storyboard.scenes:
        return None
    concat_intro = _intro_clip_from_concat(project_root, variant=variant)
    if concat_intro is not None:
        return ReviewTarget("intro", concat_intro, "transition", style=style)
    first_scene = _resolve_scene_clip(project_root, storyboard, storyboard.scenes[0].id, variant=variant)
    if first_scene is None:
        return None
    duration = float(storyboard.theme.intro_transition_duration_sec or "0.9")
    page_count = int(storyboard.theme.intro_transition_page_count or "2")
    width, height = get_resolution(storyboard.aspect_ratio)
    from pipeline.stages.compose import ComposeStage

    compose_dir = project_root / "compose"
    intro_src = ComposeStage()._book_start_plate(compose_dir, width, height, 30, duration)
    try:
        cfg = TransitionConfig(
            style=style,
            duration_sec=duration,
            sfx=None,
            page_count=page_count if style in BOOK_PAGE_STYLES else None,
            renderer_mode=storyboard.theme.intro_transition_renderer_mode or None,
            asset_path=storyboard.theme.intro_transition_asset_path or None,
            asset_source=storyboard.theme.intro_transition_asset_source or None,
            asset_source_url=storyboard.theme.intro_transition_asset_source_url or None,
            asset_license=storyboard.theme.intro_transition_asset_license or None,
            asset_notes=storyboard.theme.intro_transition_asset_notes or None,
        )
    except ValueError:
        return None
    key = transition_cache_key(intro_src, first_scene.path, cfg)
    clip = compose_dir / "transitions" / f"{key}.mp4"
    if not clip.exists():
        return None
    return ReviewTarget("intro", clip, "transition", style=style)


def _intro_clip_from_concat(project_root: Path, *, variant: str) -> Path | None:
    suffix = "_no_overlay" if variant == "no_overlay" else ""
    concat = project_root / "compose" / f"concat_list{suffix}.txt"
    if not concat.exists():
        return None
    for line in concat.read_text(encoding="utf-8").splitlines():
        match = re.match(r"file '(.+)'", line)
        if not match:
            continue
        candidate = Path(match.group(1))
        if "transitions" in candidate.parts and candidate.exists():
            return candidate
        return None
    return None


def _resolve_scene_clip(
    project_root: Path,
    storyboard: Storyboard,
    scene_id: str,
    *,
    variant: str,
) -> ReviewTarget | None:
    frame_style = storyboard.theme.frame_style or ""
    frame_suffix = f"_{frame_style}" if frame_style else ""
    scenes_dir = project_root / "compose" / "scenes"
    candidates: list[Path] = []
    if variant == "no_overlay":
        candidates.append(scenes_dir / f"{scene_id}_final_no_overlay{frame_suffix}.mp4")
    candidates.extend([
        scenes_dir / f"{scene_id}_final{frame_suffix}.mp4",
        scenes_dir / f"{scene_id}_final_no_overlay.mp4",
        scenes_dir / f"{scene_id}_final.mp4",
    ])
    for candidate in candidates:
        if candidate.exists():
            return ReviewTarget(f"{scene_id}_scene", candidate, "scene")
    return None


def _extract_scaled_frames(clip: Path, frames_dir: Path, *, scale_width: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            f"scale={scale_width}:-1",
            str(frames_dir / "frame_%05d.png"),
        ],
        check=True,
    )


def _frame_metric(
    idx: int,
    time_sec: float,
    image: Image.Image,
    gray: Image.Image,
    edge: Image.Image,
) -> FrameMetric:
    luma = _mean_luma(gray)
    dark_ratio = sum(gray.histogram()[:8]) / (gray.width * gray.height)
    edge_mean = _mean_luma(edge)
    center_brown_score = _center_brown_score(image)
    cover_gold_detail_ratio = _cover_gold_detail_ratio(image)
    brown_cover_like = _brown_cover_like(image, edge_mean)
    blank_like = 132 <= luma <= 238 and edge_mean < 22.0 and not brown_cover_like
    return FrameMetric(
        frame=idx,
        time_sec=time_sec,
        luma_mean=luma,
        dark_ratio=dark_ratio,
        edge_mean=edge_mean,
        center_brown_score=center_brown_score,
        cover_gold_detail_ratio=cover_gold_detail_ratio,
        blank_like=blank_like,
        brown_cover_like=brown_cover_like,
    )


def _center_brown_score(image: Image.Image) -> float:
    w, h = image.size
    band_w = max(2, int(w * 0.035))
    side_w = max(2, int(w * 0.045))
    y0, y1 = int(h * 0.14), int(h * 0.86)
    cx = w // 2
    center = image.crop((cx - band_w // 2, y0, cx + band_w // 2, y1))
    left = image.crop((max(0, cx - int(w * 0.16) - side_w), y0, max(1, cx - int(w * 0.16)), y1))
    right = image.crop((min(w - 1, cx + int(w * 0.16)), y0, min(w, cx + int(w * 0.16) + side_w), y1))
    c = _rgb_mean(center)
    left_rgb = _rgb_mean(left)
    right_rgb = _rgb_mean(right)
    side_luma = (_luma(left_rgb) + _luma(right_rgb)) / 2
    center_luma = _luma(c)
    center_std = float(ImageStat.Stat(center.convert("L")).stddev[0])
    brown_chroma = max(0.0, c[0] - c[2]) * 0.25 + max(0.0, c[0] - c[1]) * 0.15
    if (
        not (c[0] > c[1] > c[2])
        or center_luma < 38.0
        or brown_chroma < 8.0
        or center_std > 36.0
    ):
        return 0.0
    return max(0.0, side_luma - center_luma) + brown_chroma


def _brown_cover_like(image: Image.Image, edge_mean: float) -> bool:
    w, h = image.size
    crop = image.crop((int(w * 0.08), int(h * 0.10), int(w * 0.92), int(h * 0.82)))
    r, g, b = _rgb_mean(crop)
    luma = _luma((r, g, b))
    return r > g > b and 38 <= luma <= 130 and edge_mean < 20.0


def _cover_gold_detail_ratio(image: Image.Image) -> float:
    w, h = image.size
    crop = image.crop((int(w * 0.08), int(h * 0.10), int(w * 0.92), int(h * 0.82))).convert("RGB")
    data = crop.tobytes()
    if not data:
        return 0.0
    gold_pixels = 0
    for idx in range(0, len(data), 3):
        r = data[idx]
        g = data[idx + 1]
        b = data[idx + 2]
        if r > 145 and g > 95 and b < 95 and r - g > 28 and g - b > 20:
            gold_pixels += 1
    return gold_pixels / max(1, crop.width * crop.height)


def _rgb_mean(image: Image.Image) -> tuple[float, float, float]:
    stat = ImageStat.Stat(image.convert("RGB"))
    return float(stat.mean[0]), float(stat.mean[1]), float(stat.mean[2])


def _luma(rgb: tuple[float, float, float]) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _mean_luma(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).mean[0])


def _hist_percentile(image: Image.Image, percentile: float) -> float:
    total = image.width * image.height
    target = total * percentile
    seen = 0
    for idx, count in enumerate(image.convert("L").histogram()):
        seen += count
        if seen >= target:
            return float(idx)
    return 255.0


def _distinct_motion_bins(values: list[float], bins: int = 8) -> int:
    if not values:
        return 0
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return 1
    seen: set[int] = set()
    for value in values:
        idx = min(bins - 1, int((value - low) / (high - low) * bins))
        seen.add(idx)
    return len(seen)


def _first_delta_above(delta_metrics: list[DeltaMetric], threshold: float) -> DeltaMetric | None:
    return next((m for m in delta_metrics if m.mean_abs_delta > threshold), None)


def _parse_rate(raw: str) -> float:
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        return float(numerator) / max(1.0, float(denominator))
    return float(raw)


def _status_for_findings(findings: list[ReviewFinding], *, category: str) -> ReviewStatus:
    if category == "technical":
        relevant = {"black_or_near_black_frame"}
    else:
        relevant = {
            "static_scene_hold",
            "repeated_motion_spikes",
            "motion_spike",
            "blank_page_dominance",
            "center_brown_column_artifact",
            "late_reveal_pulse",
            "intro_empty_brown_cover",
        }
    severities = [f.severity for f in findings if f.type in relevant]
    if "fail" in severities:
        return "fail"
    if "warn" in severities:
        return "warn"
    return "pass"


def _label_image(img: Image.Image, label: str) -> Image.Image:
    label_h = 28
    out = Image.new("RGB", (img.width, img.height + label_h), "white")
    out.paste(img, (0, label_h))
    draw = ImageDraw.Draw(out)
    draw.rectangle((0, 0, img.width, label_h), fill=(20, 20, 20))
    draw.text((8, 7), label, fill=(245, 245, 245))
    return out


def _save_grid(images: list[Image.Image], out: Path, *, title: str) -> None:
    if not images:
        return
    cols = min(6, len(images))
    rows = math.ceil(len(images) / cols)
    pad = 10
    title_h = 38
    cell_w = max(img.width for img in images)
    cell_h = max(img.height for img in images)
    canvas = Image.new(
        "RGB",
        (cols * cell_w + (cols + 1) * pad, title_h + rows * cell_h + (rows + 1) * pad),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 12), title, fill=(20, 20, 20))
    for idx, img in enumerate(images):
        x = pad + (idx % cols) * (cell_w + pad)
        y = title_h + pad + (idx // cols) * (cell_h + pad)
        canvas.paste(img, (x, y))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)


def _draw_series(
    draw: ImageDraw.ImageDraw,
    values: list[float],
    box: tuple[int, int, int, int],
    maxv: float,
    *,
    fill: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    pts = []
    for idx, value in enumerate(values):
        x = left + idx * (right - left) / max(1, len(values) - 1)
        y = bottom - (value / maxv) * (bottom - top)
        pts.append((x, y))
    if len(pts) > 1:
        draw.line(pts, fill=fill, width=2)
    for x, y in pts:
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=fill)


def _render_markdown(reviews: list[ClipReview]) -> str:
    lines = ["# Animation Review", ""]
    for review in reviews:
        lines.extend([
            f"## {review.label}",
            "",
            f"- clip: `{review.clip}`",
            f"- kind: {review.kind}",
            f"- duration: {review.duration_sec:.3f}s",
            f"- fps: {review.fps:.2f}",
            f"- frames: {review.frame_count}",
            f"- technical_status: {review.technical_status}",
            f"- motion_status: {review.motion_status}",
            f"- agent_review_status: {review.agent_review_status}",
            f"- confidence: {review.confidence}",
            f"- median frame delta: {float(review.stats.get('delta_median', 0)):.2f}",
            f"- max frame delta: {float(review.stats.get('delta_max', 0)):.2f}",
            f"- blank-like frames: {int(review.stats.get('blank_like_frame_count', 0))}",
            f"- center-column frames: {int(review.stats.get('center_brown_column_frame_count', 0))}",
            "- findings:",
        ])
        if review.findings:
            for finding in review.findings:
                where = ""
                if finding.frame is not None and finding.time_sec is not None:
                    where = f" at f{finding.frame} / {finding.time_sec:.2f}s"
                suggestion = f" Suggestion: {finding.suggestion}" if finding.suggestion else ""
                lines.append(
                    f"  - {finding.severity}: {finding.type}{where} - "
                    f"{finding.message}{suggestion}"
                )
        else:
            lines.append("  - none")
        lines.append("- artifacts:")
        for name, path in review.artifacts.items():
            lines.append(f"  - {name}: `{path}`")
        lines.append("")
    return "\n".join(lines)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
