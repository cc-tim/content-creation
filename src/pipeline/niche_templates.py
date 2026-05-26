from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

TEMPLATES_PATH = Path(__file__).parent.parent.parent / "configs" / "niche_intro_templates.toml"


@dataclass
class NicheTemplate:
    niche: str
    intro_type: str           # "generated_image" | "text_card" | "slide"
    intro_prompt_hint: str    # injected into Claude prompt for s1
    visual_style: str         # 30-word style descriptor for all generated images
    anchor_prompt: str        # prompt for generating the niche anchor image
    rationale: str = ""
    medium_hint: str = ""
    palette: str = ""
    subject_bias: str = ""
    universal_rules: str = ""


_SPLIT_FIELDS = ("medium_hint", "palette", "subject_bias", "universal_rules")


def _auto_split_visual_style(visual_style: str) -> dict[str, str]:
    """Best-effort split for legacy template strings without explicit fields."""
    split: dict[str, list[str]] = {field: [] for field in _SPLIT_FIELDS}

    for raw_part in visual_style.split(","):
        part = raw_part.strip()
        if not part:
            continue
        lower = part.lower()
        if lower.startswith("no ") or "no text" in lower or "no clutter" in lower:
            split["universal_rules"].append(part)
        elif (
            "sketch" in lower
            or "hand-drawn" in lower
            or "illustration" in lower
            or "watercolor" in lower
            or "painted" in lower
            or lower in {"cinematic still", "documentary aesthetic"}
        ):
            split["medium_hint"].append(part)
        elif (
            "background" in lower
            or "tone" in lower
            or "lighting" in lower
            or "contrast" in lower
            or "desaturated" in lower
            or "palette" in lower
        ):
            split["palette"].append(part)
        elif (
            "domestic" in lower
            or "family" in lower
            or "duo" in lower
            or "parent" in lower
            or "child" in lower
            or "across scenes" in lower
        ):
            split["subject_bias"].append(part)
        else:
            split["universal_rules"].append(part)

    return {field: ", ".join(parts) for field, parts in split.items()}


def load_niche_template(niche: str) -> NicheTemplate | None:
    """Return the template for *niche*, or None if not found."""
    if not TEMPLATES_PATH.exists():
        return None
    with open(TEMPLATES_PATH, "rb") as f:
        data = tomllib.load(f)
    if niche not in data:
        return None
    d = data[niche]
    split_values = {field: d.get(field, "") for field in _SPLIT_FIELDS}
    if not any(field in d for field in _SPLIT_FIELDS):
        split_values = _auto_split_visual_style(d["visual_style"])
    return NicheTemplate(
        niche=niche,
        intro_type=d["intro_type"],
        intro_prompt_hint=d["intro_prompt_hint"],
        visual_style=d["visual_style"],
        anchor_prompt=d["anchor_prompt"],
        rationale=d.get("rationale", ""),
        **split_values,
    )


def save_niche_template(template: NicheTemplate) -> None:
    """Append or update *template* in the TOML file."""
    existing: dict[str, dict[str, str]] = {}
    if TEMPLATES_PATH.exists():
        with open(TEMPLATES_PATH, "rb") as f:
            existing = tomllib.load(f)

    existing[template.niche] = {
        "intro_type": template.intro_type,
        "intro_prompt_hint": template.intro_prompt_hint,
        "visual_style": template.visual_style,
        "medium_hint": template.medium_hint,
        "palette": template.palette,
        "subject_bias": template.subject_bias,
        "universal_rules": template.universal_rules,
        "anchor_prompt": template.anchor_prompt,
        "rationale": template.rationale,
    }

    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(_to_toml(existing), encoding="utf-8")


def _to_toml(data: dict[str, dict[str, str]]) -> str:
    """Simple TOML serializer for flat string-value sections."""
    lines: list[str] = []
    for section, fields in data.items():
        lines.append(f"[{section}]")
        for k, v in fields.items():
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        lines.append("")
    return "\n".join(lines)
