from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class RequiredImage(BaseModel):
    path: str
    role: str | None = None
    caption: str | None = None


class RequiredClip(BaseModel):
    path: str
    role: str | None = None
    caption: str | None = None


class Manifest(BaseModel):
    intent: str | None = None
    video_brief: str | None = None
    verbatim_lines: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    required_images: list[RequiredImage] = Field(default_factory=list)
    required_clips: list[RequiredClip] = Field(default_factory=list)
    required_sequence: list[str] = Field(default_factory=list)

    @property
    def is_video_intent(self) -> bool:
        return self.intent == "video"


class Explainer(BaseModel):
    path: Path
    title: str
    domain: str
    manifest: Manifest
    body: str

    model_config = {"arbitrary_types_allowed": True}


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def load_explainer(path: Path) -> Explainer:
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path} has no YAML frontmatter")

    fm_raw, body = match.group(1), match.group(2)
    fm = yaml.safe_load(fm_raw) or {}

    manifest = Manifest(
        intent=fm.get("intent"),
        video_brief=fm.get("video_brief"),
        verbatim_lines=list(fm.get("verbatim_lines") or []),
        key_facts=list(fm.get("key_facts") or []),
        required_images=[
            RequiredImage(**img) if isinstance(img, dict) else RequiredImage(path=img)
            for img in (fm.get("required_images") or [])
        ],
        required_clips=[
            RequiredClip(**clip) if isinstance(clip, dict) else RequiredClip(path=clip)
            for clip in (fm.get("required_clips") or [])
        ],
        required_sequence=list(fm.get("required_sequence") or []),
    )

    return Explainer(
        path=path,
        title=str(fm.get("title", "")),
        domain=str(fm.get("domain", "")),
        manifest=manifest,
        body=body,
    )
