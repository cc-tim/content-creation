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


def _intro_template_block(template) -> str:
    """Build the s1 constraint block for the Claude storyboard prompt."""
    if template is None:
        return (
            "INTRO CONSTRAINT (Scene s1):\n"
            "- s1 must NOT use type 'clip' or 'still_frame' from source.\n"
            "- Use 'generated_image', 'text_card', or 'slide' for s1.\n"
            "- No niche intro template found; choose a visually original opening."
        )
    return (
        f"INTRO CONSTRAINT (Scene s1 — niche: {template.niche}):\n"
        f"- s1 MUST use visual type '{template.intro_type}'.\n"
        f"- Never use 'clip' or 'still_frame' for s1.\n"
        f"- Prompt hint for s1: {template.intro_prompt_hint}"
    )


def _validate_clip_budget(scenes: list[dict], max_pct: float = 0.60) -> list[str]:
    """Return list of warning strings if clip budget exceeded (soft, never blocks)."""
    source_types = {"clip", "still_frame"}
    clip_count = sum(
        1 for s in scenes
        if (s.get("visual") or {}).get("type") in source_types
    )
    max_clips = max(1, int(len(scenes) * max_pct))
    if clip_count > max_clips:
        return [
            f"Clip budget warning: {clip_count}/{len(scenes)} scenes use source clips "
            f"(soft limit: {max_clips} at {int(max_pct * 100)}%)."
        ]
    return []


def build_direct_prompt(
    knowledge: Knowledge,
    locale: str,
    fmt: str = "standard",
    tone: str = "dramatic",
    strategies_text: str = "",
    reference_storyboard_json: str | None = None,
    constraints_text: str = "",
    clip_budget_text: str = "",
    intro_template_text: str = "",
    niche: str | None = None,
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
        duration_line = constraints_text if constraints_text else "Target 10 minutes total."
        argument_block = """STEP 1 — ORGANIZE BY ARGUMENT, NOT TIMELINE:
Before assigning scenes to sections, declare 3-6 talking_points. Each is one
argument the video advances — NOT a time bucket. Example for a product-safety video:
  • "The product solved a real parental need"      (rise)
  • "Why the 70s was the breakthrough"             (rise)
  • "Behind the success, a hidden injury cost"     (turn)
  • "Why regulation took 40 years"                 (consequence)
  • "Three products share one name"                (payoff)
Every scene must either LAND a talking point or be a PIVOT scene whose only
job is the turn between two points ("But while…", "And yet…"). Sections
(hook/context/rising/...) describe arc POSITION; talking points describe what
is actually being said.

STEP 2 — PROPORTIONAL DWELL:
If the video pivots from positive→critical (or vice versa), develop the rising
side across ≥4 scenes BEFORE the pivot, including:
  - motivation (why this thing exists / what need it solves)
  - the breakthrough moment (why it succeeded / what changed)
  - peak-moment dwell (the cultural high, with concrete texture)
  - a NAMED PIVOT SCENE whose only purpose is the turn
NEVER let a single scene carry both "peak success" and "first sign of failure"
— that collapses the arc into a year list. The viewer needs to invest in the
rise before they can feel the fall.

STEP 3 — CONNECTIVE TISSUE:
For each scene after s1, decide its relation_to_prev:
  escalates | contrasts | causally_explains | qualifies | pivots | restates
If three or more consecutive scenes are all "escalates" with no other relation,
you are writing a chronicle — restructure into talking points instead.

"""

        if niche == "parenting":
            structure = f"""VIDEO STRUCTURE (standard format, 8-12 minutes, parenting/education):

{argument_block}SECTION BINS (allocation, not the organizing principle):
- hook (0-45s, 2-3 scenes): {hook_guidance}
- context (45s-3min, 4-6 scenes): Background. Holds the entire "rise" arc.
- rising (3-7min, 8-12 scenes): The injury/risk side after the pivot
- climax (7-9min, 3-5 scenes): Peak tension
- aftermath (9-10min, 2-3 scenes): Resolution, consequences
- analysis (10-12min, 4-6 scenes): Commentary, broader implications

Target 30-40 scenes total. Each scene narration_est_sec 10-15 (avg ~13s).
pause_after_sec: 0.3-0.5s within a section, 0.5-0.8s between sections,
0.8-1.2s hook→context, 0.8s before a pivot scene. Never use 0.0 — even 0.3s
makes breathing room. {duration_line}

VISUAL CONTINUITY: Images must feel like they belong in the same visual world.
- If the same person/setting appears in multiple scenes, describe them identically.
- Use 2-3 settings max (e.g., "living room", "bedroom", "park"). Revisit, don't invent new ones.
- Prompt subjects consistently for character identity across scenes.
  Good: "parent kneeling at toddler height, worried" → "same parent beside child, patient"
  Bad: "mother in dress" → "woman in sweater" → "parent with glasses" (three different people)"""
        else:
            structure = f"""VIDEO STRUCTURE (standard format, 10-15 minutes):

{argument_block}SECTION BINS (allocation, not the organizing principle):
- hook (0-30s): {hook_guidance}
- context (30s-2min): Background. Holds the entire "rise" arc.
- rising (2-6min): The injury/risk side after the pivot
- climax (6-8min): Peak tension
- aftermath (8-10min): Resolution, consequences
- analysis (10-12min): Commentary, broader implications

Use 15-25 scenes. {duration_line}"""
        visual_note = (
            "Prefer generated_image for educational content (still images + narration work best). "
            "Mix visual types: clip for action, map for geography, "
            "namecard for intros, text_card for key facts."
        ) if niche == "parenting" else (
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

    constraints_parts = []
    if constraints_text:
        constraints_parts.append(constraints_text)
    if clip_budget_text:
        constraints_parts.append(clip_budget_text)
    if intro_template_text:
        constraints_parts.append(intro_template_text)
    if constraints_parts:
        constraints_section = "\n\n" + "\n\n".join(constraints_parts) + "\n"
    else:
        constraints_section = ""

    return f"""You are a video director. Create a scene-by-scene storyboard \
from the knowledge below.
This is NOT a translation — it is a cultural adaptation creating ORIGINAL content.

LOCALE: {locale}
LANGUAGE: {locale_instruction}
TONE: {tone}
{strategies_block}{reference_block}
{structure}
{constraints_section}
VISUAL TYPES (assign one per scene):
- clip: {{"type": "clip", "source": "primary", "start_sec": N, "end_sec": N}}
- text_card: {{"type": "text_card", "text": "...", "background": "#1a1a2e"}}
- map: {{"type": "map", "query": "Location", "style": "satellite"}}
- namecard: {{"type": "namecard", "name": "...", "role": "..."}}
- generated_image: {{"type": "generated_image", "prompt": "subject + action + spatial layout + mood — NO style words"}}
  Optional: "style_modifier": "single mood modifier e.g. 'darker tone' or 'soft light'" (NOT full style descriptors)
  RULE: visual.prompt = concept only. Style is global (theme.visual_style). Do NOT write 'watercolor', 'sketch', 'realistic', etc. in prompt.
  Good: "exhausted parent kneeling at toddler eye level in hallway, worried expression"
  Bad:  "warm watercolor illustration of parent kneeling"
- slide: {{"type": "slide", "title": "...", "bullets": ["..."]}}
- chart: {{"type": "chart", "chart_type": "stat_big_number|proportion_blocks|timeline|bar|comparison|line", "title": "...", "data": {{...}}, "source_credit": "optional"}}
  Use when the scene's CORE message IS a number, a proportion, a sequence of years, a ranking, a two-way contrast, or a TREND OVER TIME.
  If the scene names a REAL datapoint, PREFER chart over slide+text — a stat deserves a real visualization, not a bullet.
  Copy the per-type data shape EXACTLY (the schema differs per chart_type):
  - stat_big_number: {{"chart_type": "stat_big_number", "title": "Cumulative injuries", "data": {{"value": "230,676", "unit": "children", "context": "1990–2014"}}}}
  - proportion_blocks: {{"chart_type": "proportion_blocks", "title": "Where falls happen", "data": {{"label": "74% stair falls", "ratio": 0.74, "secondary_label": "26% other", "secondary_ratio": 0.26}}}}
  - timeline: {{"chart_type": "timeline", "title": "Two decades", "data": [{{"year": 1990, "label": "20,650 ER visits"}}, {{"year": 2014, "label": "230k cumulative"}}]}}
  - bar: {{"chart_type": "bar", "title": "Injury mechanisms", "data": {{"x": ["stair falls", "tip-overs", "burns"], "y": [74, 13, 6], "y_unit": "%"}}}}
  - comparison: {{"chart_type": "comparison", "title": "Speed vs reaction", "data": {{"left": {{"label": "Sit-in walker", "value": "3 ft/s"}}, "right": {{"label": "Adult reaction", "value": "0.7 s"}}}}}}
  - line: {{"chart_type": "line", "title": "US ER visits per year", "data": {{"points": [{{"x": 1990, "y": 20650}}, {{"x": 1999, "y": 8800}}, {{"x": 2014, "y": 2001}}], "markers": [{{"x": 1997, "label": "ASTM F977"}}, {{"x": 2010, "label": "CPSC mandatory"}}]}}}}
    USE `line` (not `timeline`) when the scene's CORE is the TREND ITSELF — a series of numeric Y values per X (typically year), with optional event markers on the same axis. USE `timeline` for unconnected dated events without a quantitative axis. A falling injury rate, a price curve, a search-interest line: those are `line`. A sequence of "1990 → 2001 → 2014" event labels with no numbers: that's `timeline`.
  RULE: stat_big_number value must be <= 8 chars. Charts carry their own title — do NOT also add a text overlay.

  ANIMATION (optional, for line / bar / stat_big_number only): add an `animate` block on the visual:
    "animate": {{"enabled": true, "reveal_duration_sec": 4.0, "easing": "ease_out_cubic"}}
  - `reveal_duration_sec` MUST be <= scene narration duration - 0.5s (the renderer holds the final frame for the last 0.5s so the chart settles; longer reveals are rejected at compose time). If omitted, defaults to min(narration_sec * 0.6, 5.0).
  - `easing` is "ease_out_cubic" (default — fast arrival, settle) or "linear".
  - Use animation when the SCENE'S NARRATION ITSELF builds momentum to the data ("By 2014, ER visits dropped to about 2,000 — ninety percent below the 1990 peak" → animated line draws the fall as the narration delivers the verdict). Static is fine when the scene presents the number without dramatic arrival.
  - Animation is a VISUAL-QUALITY lift only; it does NOT extend the scene. Pick narration_est_sec based on the line, not on how long the chart "should" play.
- still_frame: {{"type": "still_frame", "source": "primary", "timestamp_sec": N}}

{visual_note}

For each scene's visual, include:
- "confidence": "high|medium|low"
  - high: clear source image OR clear data → chart (numbers/proportions/years) OR pure key-fact → text_card
  - medium: type fits but other options would also work
  - low: no obviously-correct choice; user should pick
- "rationale": "one sentence why this visual type was chosen for this scene"

OVERLAY (optional per scene, renders on top of visual):
- title: {{"type": "title", "text": "..."}}
- text: {{"type": "text", "text": "..."}}
- namecard: {{"type": "namecard", "name": "...", "role": "..."}}

Each scene references fact IDs from the knowledge base.

For each scene, write a language-neutral beat (NOT narration text).

BEAT TONE BY SECTION (important — controls how the narration writer downstream phrases each scene):
- hook / context: state the fact neutrally. Avoid words like "Emphasizes...", "Reveals the shocking...",
  "Underscores the dramatic...", "Highlights how unchanged...". Use plain verbs: "Notes that...",
  "Introduces...", "Establishes...", "Shows...". Hook scenes need curiosity, not climax.
- rising: may use mild escalation words ("Builds tension via...", "Raises the stakes...").
- climax / aftermath / punchline: dramatic verbs allowed ("Delivers the shocking moment...",
  "Reveals the irreversible cost...", "Lands the final twist...").
- analysis / content: explanatory tone ("Explains why...", "Compares X and Y...").
Bad beat (hook): "Emphasizes the unchanged nature of walker design over 600 years"
Good beat (hook): "Notes that the walker concept persisted in similar form across nearly six centuries"
Rule: the dramatized framing must be earned by where the scene sits in the arc; if you push a
climax-style beat into a hook scene, the downstream narration will pick up that tone and read as
artificial AI writing.

Return ONLY valid JSON:
{{
  "title": "YouTube title in target locale, ~60 chars, applying loaded strategies",
  "description": "YouTube description in target locale, 2-3 paragraphs, crediting sources",
  "talking_points": [
    {{"id": "tp1", "claim": "one-line argument this point advances", "scene_ids": ["s4", "s5"]}}
  ],
  "scenes": [
    {{
      "id": "s1",
      "section": "hook|context|rising|climax|aftermath|analysis|content|punchline",
      "talking_point_id": "tp1 (or null for pivot scenes)",
      "relation_to_prev": "escalates|contrasts|causally_explains|qualifies|pivots|restates (omit on s1)",
      "beat": "language-neutral one-line statement of what this scene accomplishes (intent, NOT narration text, NOT a wording summary)",
      "narration_est_sec": 13,
      "facts_ref": ["f1"],
      "visual": {{"type": "...", "confidence": "high|medium|low", "rationale": "one sentence why this type was chosen", ...}},
      "overlay": null or {{"type": "...", "text": "..."}},
      "pause_after_sec": 0.5
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
- generated_image: {{"type": "generated_image", "prompt": "concept only — no style words"}}
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
            "localizations": {
                "type": "object",
                "properties": {
                    "en": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
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
    mla: bool = False,
) -> tuple[str, str]:
    facts_text = "\n".join(f"- {f.get('text', '')}" for f in knowledge_facts[:10])
    system = f"""You are writing YouTube metadata for a channel with this voice:

{profile.voice_guide}

Constraints:
- Title ≤ 100 chars, emotionally resonant, no clickbait
- Description ≤ 5000 chars — follow the structure below exactly
- Tags total (sum + commas) ≤ 500 chars
- Write in locale {locale}

Description structure (in order):
1. Open with a sharp question the target viewer is already carrying in their head — the pain or doubt they feel before watching
2. One paragraph introducing the core research insight or reframe the video delivers, anchored to its origin (e.g. "美國兒童發展研究發現...")
3. One sentence naming the video's structural approach (e.g. "這支影片透過三個真實案例...")
4. A short bullet list (3 items, "你會學到：") — each item names a concrete skill or reframe the viewer walks away with
5. Close with a single-sentence call-to-action question that mirrors the video's ending reframe

Do NOT summarise the narration or retell the story. Write from the perspective of the viewer's problem, not the content's storyline.

Return via the emit_metadata tool. Do not output prose."""
    mla_instruction = ""
    if mla:
        mla_instruction = """

Also produce English metadata in a "localizations" key:
{
  "localizations": {
    "en": { "title": "...", "description": "..." }
  }
}
The English title and description should convey the same content as the primary locale metadata but written for an English-speaking audience."""
    user = f"""Source URL: {source_url}

Storyboard synopsis:
{storyboard_synopsis}

Relevant facts for credit-worthy claims:
{facts_text or "(none)"}

Generate title, description, tags, and related metadata fields.{mla_instruction}"""
    return system, user


def _locale_footer(locale: str, source_url: str) -> str:
    # Footer removed — source credits and AI disclosure are not appended by default.
    # Add explicitly via `pipeline metadata set` if the operator wants them.
    return ""


def write_metadata_for_project(
    *,
    work_dir: Path,
    profile,
    locale: str,
    source_url: str,
    storyboard_synopsis: str,
    knowledge_facts: list[dict],
    regenerate: bool = False,
    mla: bool = False,
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
        mla=mla,
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

        from pipeline.constraints import ProjectConstraints

        constraints = ProjectConstraints.load(ctx.work_dir)
        constraints_text = constraints.duration_instruction() if constraints else ""
        if constraints_text:
            logger.info("direct.constraints_active", instruction=constraints_text)

        from pipeline.niche_templates import load_niche_template

        clip_budget_text = ""
        if constraints:
            estimated_count = 4 if self.fmt == "short" else 20
            clip_budget_text = constraints.clip_budget_instruction(scene_count=estimated_count)

        niche_template = None
        if ctx.niche and ctx.niche != "none":
            niche_template = load_niche_template(ctx.niche)
        intro_template_text = _intro_template_block(niche_template)

        knowledge = Knowledge.load(ctx.knowledge_path)
        client = get_anthropic_client()
        config = PipelineConfig()

        prompt = build_direct_prompt(
            knowledge, ctx.locale, self.fmt, self.tone,
            strategies_text=strategies_text,
            reference_storyboard_json=reference_storyboard_json,
            constraints_text=constraints_text,
            clip_budget_text=clip_budget_text,
            intro_template_text=intro_template_text,
            niche=ctx.niche,
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
        for scene in result.get("scenes", []):
            scene.setdefault("narration", "")

        # Build storyboard
        storyboard = Storyboard.from_dict(
            {
                "version": 1,
                "format": self.fmt,
                "target_duration_sec": 60 if self.fmt == "short" else 720,
                "aspect_ratio": "9:16" if self.fmt == "short" else "16:9",
                "primary_locale": ctx.locale,
                "title": result.get("title"),
                "description": result.get("description"),
                **{k: v for k, v in result.items() if k not in ("title", "description")},
            }
        )

        scene_dicts = [s.to_dict() for s in storyboard.scenes]
        max_pct = constraints.max_source_clip_pct if constraints else 0.60
        budget_warnings = _validate_clip_budget(scene_dicts, max_pct)
        for w in budget_warnings:
            logger.warning("direct.clip_budget", warning=w)

        if storyboard.scenes:
            s1_type = storyboard.scenes[0].visual.get("type", "")
            if s1_type in ("clip", "still_frame"):
                logger.warning(
                    "direct.intro_constraint_violated",
                    scene="s1",
                    visual_type=s1_type,
                    hint="Claude ignored intro constraint — edit s1 visual manually or rescene",
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

        from pipeline.director.storyboard_validator import (
            format_visual_decision_table,
            raise_for_validation_errors,
        )

        print(
            format_visual_decision_table(
                storyboard,
                ctx.work_dir,
                project_id=ctx.project_id,
            )
        )
        raise_for_validation_errors(storyboard, ctx.work_dir)

        # Backwards compat: populate old fields
        ctx.story_structure = {
            "beats": [
                {"id": s.id, "section": s.section, "beat": s.beat}
                for s in storyboard.scenes
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
                        f"{s.section}: {s.beat}" for s in storyboard.scenes
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
                        mla=ctx.mla,
                    )
            else:
                logger.warning(
                    "direct.metadata.skipped",
                    reason=f"channel config not found at {channel_cfg_path}",
                )

        return ctx
