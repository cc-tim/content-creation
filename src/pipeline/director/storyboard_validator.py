from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError

from pipeline.composer.base import VISUAL_TYPES
from pipeline.storyboard import Scene, Storyboard

Severity = Literal["error", "warn"]

_IMAGE_TYPES = {"article_image", "image"}
_STYLE_WORDS = {"watercolor", "sketch", "realistic", "anime"}
_CLIP_SOURCES = {"primary"}
_VALID_IMAGE_HEADERS = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",
    b"GIF87a",
    b"GIF89a",
)


@dataclass(frozen=True)
class SceneValidationError:
    scene_id: str
    severity: Severity
    field: str
    issue: str
    suggested_fix: str

    def to_dict(self) -> dict[str, str]:
        return {
            "scene_id": self.scene_id,
            "severity": self.severity,
            "field": self.field,
            "issue": self.issue,
            "suggested_fix": self.suggested_fix,
        }


def validate_storyboard(
    sb: Storyboard,
    project_root: Path,
    *,
    scene_ids: set[str] | None = None,
) -> list[SceneValidationError]:
    """Validate scene visuals before compose can hide broken inputs."""
    issues: list[SceneValidationError] = []
    for scene in sb.scenes:
        if scene_ids is not None and scene.id not in scene_ids:
            continue
        issues.extend(_validate_scene(scene, project_root))
    return issues


def validation_errors(
    issues: list[SceneValidationError],
) -> list[SceneValidationError]:
    return [issue for issue in issues if issue.severity == "error"]


def raise_for_validation_errors(
    sb: Storyboard,
    project_root: Path,
    *,
    scene_ids: set[str] | None = None,
) -> None:
    errors = validation_errors(
        validate_storyboard(sb, project_root, scene_ids=scene_ids)
    )
    if not errors:
        return
    joined = "\n".join(
        f"{issue.scene_id} {issue.field}: {issue.issue} "
        f"Fix: {issue.suggested_fix}"
        for issue in errors
    )
    raise ValueError(f"Storyboard visual validation failed:\n{joined}")


def visual_decisions_for_storyboard(
    sb: Storyboard,
    project_root: Path,
) -> list[dict[str, object]]:
    issues = validate_storyboard(sb, project_root)
    by_scene: dict[str, list[SceneValidationError]] = {}
    for issue in issues:
        by_scene.setdefault(issue.scene_id, []).append(issue)

    out: list[dict[str, object]] = []
    for scene in sb.scenes:
        visual = scene.visual or {}
        scene_issues = by_scene.get(scene.id, [])
        out.append({
            "scene_id": scene.id,
            "section": scene.section,
            "visual_type": str(visual.get("type") or "text_card"),
            "confidence": _visual_confidence(visual),
            "rationale": str(visual.get("rationale") or ""),
            "issues": [issue.to_dict() for issue in scene_issues],
        })
    return out


def format_visual_decision_table(
    sb: Storyboard,
    project_root: Path,
    *,
    project_id: str | int | None = None,
) -> str:
    decisions = visual_decisions_for_storyboard(sb, project_root)
    title = "Storyboard visual decisions"
    if project_id is not None:
        title += f" for project {project_id}"

    lines = [
        f"{title}:",
        "",
        "  id   section    type             conf   rationale",
    ]
    counts: dict[str, int] = {}
    low_confidence: list[str] = []
    for item in decisions:
        visual_type = str(item["visual_type"])
        confidence = str(item["confidence"])
        counts[visual_type] = counts.get(visual_type, 0) + 1
        if confidence == "low":
            low_confidence.append(str(item["scene_id"]))
        lines.append(
            "  "
            f"{str(item['scene_id'])[:4]:<4} "
            f"{str(item['section'])[:10]:<10} "
            f"{visual_type[:16]:<16} "
            f"{confidence[:5]:<5} "
            f"{str(item['rationale'])[:88]}"
        )

    if decisions:
        total = len(decisions)
        mix = ", ".join(
            f"{kind} {count * 100 // total}%"
            for kind, count in sorted(counts.items())
        )
        lines.extend(["", f"Mix: {mix}"])
    if low_confidence:
        lines.append(
            "Low-confidence scenes: "
            + ", ".join(low_confidence)
            + " — review before TTS."
        )

    blocking = [
        issue
        for item in decisions
        for issue in item["issues"]
        if isinstance(issue, dict) and issue.get("severity") == "error"
    ]
    warnings = [
        issue
        for item in decisions
        for issue in item["issues"]
        if isinstance(issue, dict) and issue.get("severity") == "warn"
    ]
    if blocking:
        lines.append(f"Validation errors: {len(blocking)} — TTS/compose is blocked.")
    if warnings:
        lines.append(f"Validation warnings: {len(warnings)} — review recommended.")
    return "\n".join(lines)


def _validate_scene(
    scene: Scene,
    project_root: Path,
) -> list[SceneValidationError]:
    visual = scene.visual or {}
    visual_type = str(visual.get("type") or "text_card")
    issues: list[SceneValidationError] = []

    if visual_type not in VISUAL_TYPES:
        issues.append(_issue(
            scene,
            "error",
            "visual.type",
            f"unknown visual type {visual_type!r}",
            f"Use one of: {', '.join(sorted(VISUAL_TYPES))}.",
        ))
        return issues

    if visual_type in _IMAGE_TYPES:
        issues.extend(_validate_image_visual(scene, visual, project_root))
    elif visual_type == "slide":
        issues.extend(_validate_slide(scene, visual))
    elif visual_type == "rich_slide":
        issues.extend(_validate_rich_slide(scene, visual))
    elif visual_type == "generated_image":
        issues.extend(_validate_generated_image(scene, visual))
    elif visual_type == "text_card":
        issues.extend(_validate_text_card(scene, visual))
    elif visual_type == "clip":
        issues.extend(_validate_clip(scene, visual, project_root))
    elif visual_type == "still_frame":
        issues.extend(_validate_still_frame(scene, visual, project_root))
    elif visual_type == "chart":
        issues.extend(_validate_chart_visual(scene, visual))
    elif visual_type == "namecard" and not str(visual.get("name") or "").strip():
        issues.append(_issue(
            scene,
            "error",
            "visual.name",
            "namecard visual has no name",
            "Add visual.name or change visual.type.",
        ))
    elif visual_type == "map" and not str(visual.get("query") or "").strip():
        issues.append(_issue(
            scene,
            "error",
            "visual.query",
            "map visual has no query",
            "Add visual.query with the location to show.",
        ))
    return issues


def _validate_image_visual(
    scene: Scene,
    visual: dict[str, Any],
    project_root: Path,
) -> list[SceneValidationError]:
    issues: list[SceneValidationError] = []
    raw_path = visual.get("path")
    if not raw_path:
        return [_issue(
            scene,
            "error",
            "visual.path",
            "file-backed visual has no path",
            "Add visual.path or change visual.type to generated_image.",
        )]

    path = _effective_visual_path(visual, project_root)
    if not path.exists():
        return [_issue(
            scene,
            "error",
            "visual.path",
            f"image path not found: {path}",
            "Replace the path or change visual.type to generated_image.",
        )]

    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size < 2048:
        issues.append(_issue(
            scene,
            "error",
            "visual.path",
            f"image file is too small to trust ({size} bytes): {path}",
            "Replace it with a real source image at normal resolution.",
        ))

    if not _has_image_header(path):
        issues.append(_issue(
            scene,
            "error",
            "visual.path",
            f"path is not a valid image: {path}",
            "Delete the corrupt source and re-download or generate a replacement.",
        ))
        return issues

    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        issues.append(_issue(
            scene,
            "error",
            "visual.path",
            f"PIL could not read image {path}: {exc}",
            "Replace the corrupt file or regenerate the visual.",
        ))
        return issues

    if width <= 0 or height <= 0:
        issues.append(_issue(
            scene,
            "error",
            "visual.path",
            f"image dimensions are invalid: {width}x{height}",
            "Replace the source image.",
        ))
    elif width < 320 or height < 180:
        issues.append(_issue(
            scene,
            "warn",
            "visual.path",
            f"image is small for video: {width}x{height}",
            "Use a higher-resolution image if the scene looks soft.",
        ))
    return issues


def _validate_slide(scene: Scene, visual: dict[str, Any]) -> list[SceneValidationError]:
    issues: list[SceneValidationError] = []
    title = str(visual.get("title") or "")
    bullets = visual.get("bullets")
    text = str(visual.get("text") or "")
    has_bullets = isinstance(bullets, list) and len(bullets) > 0
    if not ((title and has_bullets) or text):
        issues.append(_issue(
            scene,
            "error",
            "visual",
            "slide must have title+bullets or text+layout",
            "Add title and bullets, or use rich_slide-shaped text/layout.",
        ))
    if len(title) > 80:
        issues.append(_issue(
            scene,
            "warn",
            "visual.title",
            "slide title is longer than 80 characters",
            "Shorten the title so it wraps cleanly.",
        ))
    if isinstance(bullets, list) and len(bullets) > 5:
        issues.append(_issue(
            scene,
            "warn",
            "visual.bullets",
            "slide has more than 5 bullets",
            "Split the slide or shorten the bullet list.",
        ))
    return issues


def _validate_rich_slide(scene: Scene, visual: dict[str, Any]) -> list[SceneValidationError]:
    if str(visual.get("text") or visual.get("title") or "").strip():
        return []
    return [_issue(
        scene,
        "error",
        "visual.text",
        "rich_slide has no text",
        "Add visual.text or change visual.type.",
    )]


def _validate_generated_image(
    scene: Scene,
    visual: dict[str, Any],
) -> list[SceneValidationError]:
    issues: list[SceneValidationError] = []
    prompt = str(visual.get("prompt") or "").strip()
    if not prompt:
        issues.append(_issue(
            scene,
            "error",
            "visual.prompt",
            "generated_image prompt is missing",
            "Add a concrete concept prompt for the generated image.",
        ))
    elif len(prompt) < 20:
        issues.append(_issue(
            scene,
            "warn",
            "visual.prompt",
            "generated_image prompt is very short",
            "Use a subject + action + spatial layout prompt.",
        ))

    lower = prompt.lower()
    found = sorted(word for word in _STYLE_WORDS if word in lower)
    if found:
        issues.append(_issue(
            scene,
            "warn",
            "visual.prompt",
            f"prompt contains style words: {', '.join(found)}",
            "Move visual style words into theme.visual_style or visual.style_modifier.",
        ))

    style_modifier = str(visual.get("style_modifier") or "")
    if len(style_modifier) > 40:
        issues.append(_issue(
            scene,
            "warn",
            "visual.style_modifier",
            "style_modifier is longer than 40 characters",
            "Keep style_modifier to a short mood modifier.",
        ))
    return issues


def _validate_chart_visual(scene: Scene, visual: dict[str, Any]) -> list[SceneValidationError]:
    """Promote composer/chart.py:validate_chart_visual into validator errors."""
    from pipeline.composer.chart import validate_chart_visual

    duration: float | None = None
    if scene.narration_est_sec:
        duration = float(scene.narration_est_sec)

    issues_text = validate_chart_visual(visual, scene.id, duration_sec=duration)
    out: list[SceneValidationError] = []
    for msg in issues_text:
        out.append(_issue(
            scene,
            "error",
            "visual",
            msg,
            "Fix the chart schema; see composer/chart.py:CHART_TYPES for valid types.",
        ))
    return out


def _validate_text_card(scene: Scene, visual: dict[str, Any]) -> list[SceneValidationError]:
    text = str(visual.get("text") or "")
    if not text.strip():
        return [_issue(
            scene,
            "error",
            "visual.text",
            "text_card has no text",
            "Add visual.text or choose a different visual type.",
        )]
    if len(text) > 80:
        return [_issue(
            scene,
            "warn",
            "visual.text",
            "text_card text is longer than 80 characters",
            "Shorten it to fit within roughly four lines.",
        )]
    return []


def _validate_clip(
    scene: Scene,
    visual: dict[str, Any],
    project_root: Path,
) -> list[SceneValidationError]:
    issues: list[SceneValidationError] = []
    _validate_source(scene, visual, issues)
    start = _number_or_issue(scene, visual.get("start_sec"), "visual.start_sec", issues)
    end = _number_or_issue(scene, visual.get("end_sec"), "visual.end_sec", issues)
    if start is not None and end is not None:
        if end <= start:
            issues.append(_issue(
                scene,
                "error",
                "visual.end_sec",
                "clip end_sec must be greater than start_sec",
                "Set a positive clip range.",
            ))
        _validate_against_duration(scene, start, "visual.start_sec", project_root, issues)
        _validate_against_duration(scene, end, "visual.end_sec", project_root, issues)
    return issues


def _validate_still_frame(
    scene: Scene,
    visual: dict[str, Any],
    project_root: Path,
) -> list[SceneValidationError]:
    issues: list[SceneValidationError] = []
    _validate_source(scene, visual, issues)
    ts = _number_or_issue(
        scene, visual.get("timestamp_sec"), "visual.timestamp_sec", issues
    )
    if ts is not None:
        _validate_against_duration(scene, ts, "visual.timestamp_sec", project_root, issues)
    return issues


def _validate_source(
    scene: Scene,
    visual: dict[str, Any],
    issues: list[SceneValidationError],
) -> None:
    source = str(visual.get("source") or "")
    if source not in _CLIP_SOURCES:
        issues.append(_issue(
            scene,
            "error",
            "visual.source",
            f"source must be one of {sorted(_CLIP_SOURCES)}, got {source!r}",
            "Use source='primary' until additional source streams are implemented.",
        ))


def _number_or_issue(
    scene: Scene,
    value: Any,
    field: str,
    issues: list[SceneValidationError],
) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        issues.append(_issue(
            scene,
            "error",
            field,
            "timestamp must be numeric",
            "Use seconds as a number.",
        ))
        return None
    if number < 0:
        issues.append(_issue(
            scene,
            "error",
            field,
            "timestamp must be non-negative",
            "Use seconds from the start of the source media.",
        ))
        return None
    return number


def _validate_against_duration(
    scene: Scene,
    timestamp: float,
    field: str,
    project_root: Path,
    issues: list[SceneValidationError],
) -> None:
    duration = _source_duration(project_root)
    if duration is None:
        return
    if timestamp > duration:
        issues.append(_issue(
            scene,
            "error",
            field,
            f"timestamp {timestamp:g}s exceeds source duration {duration:g}s",
            "Pick a timestamp inside the source video.",
        ))


def _source_duration(project_root: Path) -> float | None:
    source = project_root / "source" / "video.mp4"
    if not source.exists():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _effective_visual_path(visual: dict[str, Any], project_root: Path) -> Path:
    refit = visual.get("refit_path")
    if refit:
        refit_path = _resolve_path(str(refit), project_root)
        if refit_path.exists():
            return refit_path
    return _resolve_path(str(visual.get("path") or ""), project_root)


def _resolve_path(raw: str, project_root: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    candidates = [project_root / path, Path.cwd() / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _has_image_header(path: Path) -> bool:
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    if head.startswith(_VALID_IMAGE_HEADERS):
        return True
    return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def _visual_confidence(visual: dict[str, Any]) -> str:
    raw = str(visual.get("confidence") or "").lower()
    if raw in {"high", "medium", "low"}:
        return raw
    return "medium"


def _issue(
    scene: Scene,
    severity: Severity,
    field: str,
    issue: str,
    suggested_fix: str,
) -> SceneValidationError:
    return SceneValidationError(
        scene_id=scene.id,
        severity=severity,
        field=field,
        issue=issue,
        suggested_fix=suggested_fix,
    )
