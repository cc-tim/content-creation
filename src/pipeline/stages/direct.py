from __future__ import annotations

import json

import structlog

from pipeline.config import PipelineConfig
from pipeline.knowledge import Knowledge
from pipeline.stages.analyze import get_anthropic_client
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.storyboard import Storyboard

logger = structlog.get_logger()

LOCALE_INSTRUCTIONS = {
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
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["zh-TW"])
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
        structure = """VIDEO STRUCTURE (standard format, 10-15 minutes):
- hook (0-30s): Most dramatic moment out of context
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
            max_tokens=8192,
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
                **result,
            }
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
        return ctx
