from __future__ import annotations

import json
from pathlib import Path

import structlog

from pipeline.config import PipelineConfig
from pipeline.knowledge import Knowledge
from pipeline.stages.analyze import get_anthropic_client
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.storyboard import Storyboard

logger = structlog.get_logger()

LOCALE_INSTRUCTIONS = {
    "en": (
        "Write in clear, conversational English. "
        "Use an authoritative but warm narrator voice appropriate for long-form YouTube content."
    ),
    "zh-TW": (
        "Write in Traditional Chinese (zh-TW), Taiwan usage conventions. "
        "Explain US-specific context (legal system, geography, policing norms) "
        "that Taiwanese audiences need. Use conversational but authoritative tone."
    ),
    "ja": (
        "Write in Japanese. Use appropriate keigo level for documentary narration. "
        "Add cultural context bridging US and Japanese norms."
    ),
    "es-MX": (
        "Write in Latin American Spanish (Mexican variant). "
        "Explain US cultural context for Latin American audiences."
    ),
}


def build_direct_prompt(
    knowledge: Knowledge,
    locale: str,
    fmt: str = "standard",
    tone: str = "dramatic",
    strategies_text: str = "",
    reference_storyboard_json: str | None = None,  # wired up in Task 9; accept here
) -> str:
    """Build Claude prompt to generate a storyboard from knowledge."""
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale) or LOCALE_INSTRUCTIONS["en"]
    knowledge_json = json.dumps(knowledge.to_dict(), indent=2, ensure_ascii=False)

    if fmt == "short":
        structure = """VIDEO STRUCTURE (Shorts format, 30-60 seconds):
- hook (0-5s): One surprising statement, no context
- content (5-40s): Explain the fun fact with visual variety
- punchline (40-50s): Witty closer + call to action

Use 2-4 scenes only. Target 45 seconds total."""
        visual_note = (
            "Prefer visual types: generated_image, text_card, slide, still_frame. "
            "Use clip only if a specific moment is visually compelling."
        )
    else:
        hook_guidance = (
            "Drop viewers into the tensest moment mid-action, no setup."
            if tone == "dramatic"
            else (
                "Pose a counterintuitive question or reveal something surprising that "
                "the viewer cannot answer yet — force them to stay. "
                "Do NOT summarize the topic or start with background."
            )
        )
        structure = f"""VIDEO STRUCTURE (standard format, 10-15 minutes):
- hook (0-30s): {hook_guidance}
- context (30s-2min): Map, people, setting, background
- rising (2-6min): Escalation of events
- climax (6-8min): Peak tension
- aftermath (8-10min): Resolution, consequences
- analysis (10-12min): Commentary, broader implications

Use 15-25 scenes. Target 12 minutes total."""
        visual_note = (
            "Mix visual types for variety: clip for action moments, map for geography, "
            "namecard for introductions, text_card for key facts, generated_image for mood."
        )

    strategies_block = f"\n{strategies_text}\n" if strategies_text else ""
    reference_block = (
        f"\nREFERENCE STORYBOARD (preserve scene count, ids, facts_ref, visual, overlay; "
        f"rewrite only narration in target locale):\n```json\n{reference_storyboard_json}\n```\n"
        if reference_storyboard_json
        else ""
    )

    return f"""You are a video director. Create a scene-by-scene storyboard \
from the knowledge below.
This is NOT a translation — it is a cultural adaptation creating ORIGINAL content.

LOCALE: {locale}
LANGUAGE: {locale_instruction}
TONE: {tone}
{strategies_block}{reference_block}
{structure}

VISUAL TYPES (assign one per scene):
- clip: {{"type": "clip", "source": "primary", "start_sec": N, "end_sec": N}}
- text_card: {{"type": "text_card", "text": "...", "background": "#1a1a2e"}}
- map: {{"type": "map", "query": "Location", "style": "satellite"}}
- namecard: {{"type": "namecard", "name": "...", "role": "..."}}
- generated_image: {{"type": "generated_image", "prompt": "description", "style": "cinematic"}}
- slide: {{"type": "slide", "title": "...", "bullets": ["..."]}}
- still_frame: {{"type": "still_frame", "source": "primary", "timestamp_sec": N}}

{visual_note}

OVERLAY (optional per scene, renders on top of visual):
- title: {{"type": "title", "text": "..."}}
- text: {{"type": "text", "text": "..."}}
- namecard: {{"type": "namecard", "name": "...", "role": "..."}}

Each scene references fact IDs from the knowledge base.

Return ONLY valid JSON:
{{
  "title": "YouTube title in target locale, ~60 chars, applying loaded strategies",
  "description": "YouTube description in target locale, 2-3 paragraphs, crediting sources",
  "scenes": [
    {{
      "id": "s1",
      "section": "hook|context|rising|climax|aftermath|analysis|content|punchline",
      "narration": "Narration text in target locale",
      "narration_est_sec": 8,
      "facts_ref": ["f1"],
      "visual": {{"type": "...", ...}},
      "overlay": null or {{"type": "...", "text": "..."}},
      "pause_after_sec": 0
    }}
  ]
}}

KNOWLEDGE BASE:
{knowledge_json}"""


async def generate_shorts_storyboards(
    knowledge: Knowledge,
    locale: str,
    count: int = 3,
    tone: str = "educational",
) -> list[Storyboard]:
    """Score facts for standalone interest and generate N short storyboards."""
    client = get_anthropic_client()
    config = PipelineConfig()

    # Ask Claude to select top facts and generate shorts
    facts_json = json.dumps(
        [{"id": f.id, "text": f.text, "tags": f.tags} for f in knowledge.facts],
        indent=2,
        ensure_ascii=False,
    )
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["zh-TW"])

    prompt = f"""From the facts below, select the {count} most interesting \
standalone facts for YouTube Shorts.

Selection criteria:
- Standalone interest: understandable without context?
- Surprise factor: counterintuitive > obvious
- Visual potential: can we show something compelling?
- Brevity: explainable in 15 seconds?

For each selected fact, generate a short storyboard (30-60 seconds, 2-4 scenes).

LOCALE: {locale}
LANGUAGE: {locale_instruction}
TONE: {tone}

Structure per Short: hook (surprising statement) → content (explain) → punchline (witty closer)

VISUAL TYPES:
- clip: {{"type": "clip", "source": "primary", "start_sec": N, "end_sec": N}}
- text_card: {{"type": "text_card", "text": "...", "background": "#1a1a2e"}}
- generated_image: {{"type": "generated_image", "prompt": "...", "style": "cinematic"}}
- slide: {{"type": "slide", "title": "...", "bullets": ["..."]}}

Return ONLY valid JSON:
{{
  "shorts": [
    {{
      "fact_id": "f1",
      "scenes": [
        {{
          "id": "s1",
          "section": "hook|content|punchline",
          "narration": "text in target locale",
          "narration_est_sec": 5,
          "facts_ref": ["f1"],
          "visual": {{"type": "...", ...}},
          "overlay": null,
          "pause_after_sec": 0
        }}
      ]
    }}
  ]
}}

FACTS:
{facts_json}"""

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]

    result = json.loads(raw_text)

    storyboards: list[Storyboard] = []
    for short_data in result["shorts"]:
        sb = Storyboard.from_dict(
            {
                "version": 1,
                "format": "short",
                "target_duration_sec": 60,
                "aspect_ratio": "9:16",
                "scenes": short_data["scenes"],
            }
        )
        storyboards.append(sb)

    return storyboards


_METADATA_TOOL = {
    "name": "emit_metadata",
    "description": "Emit YouTube metadata as structured JSON.",
    "input_schema": {
        "type": "object",
        "required": [
            "title",
            "description",
            "tags",
            "category_id",
            "default_language",
            "default_audio_language",
            "made_for_kids",
            "altered_or_synthetic_content",
        ],
        "properties": {
            "title": {"type": "string", "maxLength": 100},
            "description": {"type": "string", "maxLength": 5000},
            "tags": {"type": "array", "items": {"type": "string"}},
            "category_id": {"type": "integer"},
            "default_language": {"type": "string"},
            "default_audio_language": {"type": "string"},
            "made_for_kids": {"type": "boolean"},
            "altered_or_synthetic_content": {
                "type": "string",
                "enum": ["synthetic_voice", "altered", "none"],
            },
        },
    },
}


def _build_metadata_prompt(
    *,
    profile,
    locale: str,
    source_url: str,
    storyboard_synopsis: str,
    knowledge_facts: list[dict],
) -> tuple[str, str]:
    facts_text = "\n".join(f"- {f.get('text', '')}" for f in knowledge_facts[:10])
    system = f"""You are writing YouTube metadata for a channel with this voice:

{profile.voice_guide}

Constraints:
- Title ≤ 100 chars
- Description ≤ 5000 chars
- Tags total (sum + commas) ≤ 500 chars
- Write in locale {locale}

Return via the emit_metadata tool. Do not output prose."""
    user = f"""Source URL: {source_url}

Storyboard synopsis:
{storyboard_synopsis}

Relevant facts for credit-worthy claims:
{facts_text or "(none)"}

Generate title, description, tags, and related metadata fields."""
    return system, user


def _locale_footer(locale: str, source_url: str) -> str:
    if locale == "zh-TW":
        return f"\n\n資料來源:{source_url}\n\n本影片旁白由 AI 合成。"
    if locale == "ja":
        return f"\n\n情報源:{source_url}\n\n本動画のナレーションはAI音声です。"
    if locale == "es-MX":
        return f"\n\nFuente: {source_url}\n\nLa narración de este video fue generada por IA."
    return f"\n\nSource: {source_url}\n\nThis video uses AI-generated narration."


def write_metadata_for_project(
    *,
    work_dir: Path,
    profile,
    locale: str,
    source_url: str,
    storyboard_synopsis: str,
    knowledge_facts: list[dict],
    regenerate: bool = False,
) -> Path:
    """Generate (or preserve) metadata.json for a project.

    Returns the written path. If the file already exists and regenerate=False,
    leaves it untouched (preserves operator's hand-edits).
    """
    from pipeline.publish.metadata import Metadata, save_metadata

    path = work_dir / "metadata.json"
    if path.exists() and not regenerate:
        logger.info("direct.metadata.skipped_existing", path=str(path))
        return path

    system, user = _build_metadata_prompt(
        profile=profile,
        locale=locale,
        source_url=source_url,
        storyboard_synopsis=storyboard_synopsis,
        knowledge_facts=knowledge_facts,
    )

    client = get_anthropic_client()
    config = PipelineConfig()

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2048,
        system=system,
        tools=[_METADATA_TOOL],
        tool_choice={"type": "tool", "name": "emit_metadata"},
        messages=[{"role": "user", "content": user}],
    )

    tool_input: dict | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = block.input
            break
    if tool_input is None:
        raise RuntimeError("Claude did not return emit_metadata tool use")

    # Merge default tags (prepend, dedup preserving order)
    merged_tags: list[str] = []
    for tag in list(profile.default_tags) + list(tool_input.get("tags") or []):
        if tag not in merged_tags:
            merged_tags.append(tag)
    tool_input["tags"] = merged_tags

    tool_input.setdefault("category_id", profile.category_id)

    tool_input["description"] = tool_input["description"].rstrip() + _locale_footer(
        locale, source_url
    )

    metadata = Metadata(**tool_input)
    save_metadata(metadata, path, source_url=source_url, profile=profile.name)
    logger.info("direct.metadata.written", path=str(path), profile=profile.name)
    return path


class DirectStage(PipelineStage):
    """Generates storyboard (Layer 2) from knowledge (Layer 1).
    Replaces the old scriptwrite stage.
    """

    def __init__(self, fmt: str = "standard", tone: str = "dramatic"):
        self.fmt = fmt
        self.tone = tone

    @property
    def name(self) -> str:
        return "direct"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.knowledge_path or not ctx.knowledge_path.exists():
            raise ValueError("No knowledge base — run analyze stage first")

        logger.info("direct.start", locale=ctx.locale, format=self.fmt)

        from pipeline.strategies import load_strategies

        strategies_text = load_strategies(ctx)

        reference_storyboard_json: str | None = None
        if ctx.reference_storyboard_path and ctx.reference_storyboard_path.exists():
            reference_storyboard_json = ctx.reference_storyboard_path.read_text(encoding="utf-8")

        knowledge = Knowledge.load(ctx.knowledge_path)
        client = get_anthropic_client()
        config = PipelineConfig()

        prompt = build_direct_prompt(
            knowledge, ctx.locale, self.fmt, self.tone,
            strategies_text=strategies_text,
            reference_storyboard_json=reference_storyboard_json,
        )

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(raw_text)

        # Build storyboard
        storyboard = Storyboard.from_dict(
            {
                "version": 1,
                "format": self.fmt,
                "target_duration_sec": 60 if self.fmt == "short" else 720,
                "aspect_ratio": "9:16" if self.fmt == "short" else "16:9",
                "title": result.get("title"),
                "description": result.get("description"),
                **{k: v for k, v in result.items() if k not in ("title", "description")},
            }
        )

        if reference_storyboard_json is not None:
            ref_scenes = json.loads(reference_storyboard_json).get("scenes", [])
            if len(ref_scenes) != len(storyboard.scenes):
                logger.warning(
                    "direct.scene_drift",
                    reference_count=len(ref_scenes),
                    produced_count=len(storyboard.scenes),
                )
            else:
                ref_ids = [s.get("id") for s in ref_scenes]
                new_ids = [s.id for s in storyboard.scenes]
                if ref_ids != new_ids:
                    logger.warning(
                        "direct.scene_id_mismatch",
                        reference_ids=ref_ids,
                        produced_ids=new_ids,
                    )

        # Save storyboard
        storyboard_path = ctx.work_dir / f"storyboard_{ctx.locale}.json"
        storyboard.save(storyboard_path)
        ctx.storyboard_path = storyboard_path

        # Derive script.md for TTS
        script_text = storyboard.derive_script()
        script_dir = ctx.work_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"script_{ctx.locale}.md"
        script_path.write_text(script_text, encoding="utf-8")
        ctx.script_path = script_path

        # Backwards compat: populate old fields
        ctx.story_structure = {
            "beats": [
                {"beat": s.section, "description": s.narration[:50]} for s in storyboard.scenes
            ],
        }

        logger.info(
            "direct.complete",
            scenes=len(storyboard.scenes),
            est_duration=storyboard.estimated_duration_sec(),
        )

        # Generate metadata.json for publish (skipped when niche is None or "none")
        if ctx.niche and ctx.niche != "none":
            from pipeline.publish.channels import load_channel_config, resolve_profile

            channel_cfg_path = Path("configs/youtube_channels.toml")
            if channel_cfg_path.exists():
                cfg = load_channel_config(channel_cfg_path)
                try:
                    profile = resolve_profile(
                        cfg, niche=ctx.niche, locale=ctx.locale, override=None
                    )
                except ValueError as exc:
                    logger.warning("direct.metadata.skipped", reason=str(exc))
                else:
                    synopsis = "\n".join(
                        f"{s.section}: {s.narration[:120]}" for s in storyboard.scenes
                    )
                    write_metadata_for_project(
                        work_dir=ctx.work_dir,
                        profile=profile,
                        locale=ctx.locale,
                        source_url=ctx.source_url,
                        storyboard_synopsis=synopsis,
                        knowledge_facts=[
                            {"id": f.id, "text": f.text} for f in knowledge.facts[:10]
                        ],
                    )
            else:
                logger.warning(
                    "direct.metadata.skipped",
                    reason=f"channel config not found at {channel_cfg_path}",
                )

        return ctx
