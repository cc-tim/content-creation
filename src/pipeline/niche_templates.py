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


def load_niche_template(niche: str) -> NicheTemplate | None:
    """Return the template for *niche*, or None if not found."""
    if not TEMPLATES_PATH.exists():
        return None
    with open(TEMPLATES_PATH, "rb") as f:
        data = tomllib.load(f)
    if niche not in data:
        return None
    d = data[niche]
    return NicheTemplate(
        niche=niche,
        intro_type=d["intro_type"],
        intro_prompt_hint=d["intro_prompt_hint"],
        visual_style=d["visual_style"],
        anchor_prompt=d["anchor_prompt"],
        rationale=d.get("rationale", ""),
    )


def save_niche_template(template: NicheTemplate) -> None:
    """Append or update *template* in the TOML file."""
    existing: dict = {}
    if TEMPLATES_PATH.exists():
        with open(TEMPLATES_PATH, "rb") as f:
            existing = tomllib.load(f)

    existing[template.niche] = {
        "intro_type": template.intro_type,
        "intro_prompt_hint": template.intro_prompt_hint,
        "visual_style": template.visual_style,
        "anchor_prompt": template.anchor_prompt,
        "rationale": template.rationale,
    }

    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(_to_toml(existing), encoding="utf-8")


def _to_toml(data: dict) -> str:
    """Simple TOML serializer for flat string-value sections."""
    lines: list[str] = []
    for section, fields in data.items():
        lines.append(f"[{section}]")
        for k, v in fields.items():
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        lines.append("")
    return "\n".join(lines)
