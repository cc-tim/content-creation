from __future__ import annotations

import json
from pathlib import Path

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


def get_anthropic_client():
    """Create Anthropic client from config."""
    import anthropic
    config = PipelineConfig()
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def build_analysis_prompt(transcript: str) -> str:
    """Build the Claude prompt for story analysis."""
    return f"""Analyze this video transcript and extract two things:

1. **Story structure**: Identify the narrative beats with approximate timestamps.
   - hook: the most dramatic/attention-grabbing moment
   - context: setting, people, background
   - rising_action: escalation of events
   - climax: peak tension
   - aftermath: resolution, consequences

2. **Knowledge graph**: Extract entities, relationships, conflicts, and context that a non-US audience would need explained.

3. **Clip timestamps**: Suggest 4-8 short segments (5-15 seconds each) that would work as visual reference clips in a ported video. Focus on high-visual-impact moments.

Return ONLY valid JSON in this exact format:
{{
  "story_structure": {{
    "hook": "one-line description of the hook",
    "beats": [
      {{"timestamp": "M:SS-M:SS", "beat": "hook|context|rising_action|climax|aftermath", "description": "what happens"}}
    ],
    "emotional_arc": "tension_build|mystery_reveal|justice_served|survival|tragedy"
  }},
  "knowledge_graph": {{
    "entities": [{{"name": "...", "role": "...", "details": "..."}}],
    "location": {{"city": "...", "state": "...", "setting": "..."}},
    "conflicts": ["..."],
    "context_needed_for_target_audience": ["..."]
  }},
  "clip_timestamps": [[start_sec, end_sec], ...]
}}

TRANSCRIPT:
{transcript}"""


class AnalyzeStage(PipelineStage):
    @property
    def name(self) -> str:
        return "analyze"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.transcript_text:
            raise ValueError("No transcript available — run acquire stage first")

        logger.info("analyze.start", transcript_len=len(ctx.transcript_text))

        client = get_anthropic_client()
        config = PipelineConfig()
        prompt = build_analysis_prompt(ctx.transcript_text)

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(raw_text)

        ctx.story_structure = result["story_structure"]
        ctx.knowledge_graph = result["knowledge_graph"]
        ctx.clip_timestamps = [tuple(ts) for ts in result["clip_timestamps"]]

        # Save analysis to work_dir
        analysis_dir = ctx.work_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "structure.json").write_text(
            json.dumps(ctx.story_structure, indent=2, ensure_ascii=False)
        )
        (analysis_dir / "knowledge_graph.json").write_text(
            json.dumps(ctx.knowledge_graph, indent=2, ensure_ascii=False)
        )

        logger.info("analyze.complete", beats=len(ctx.story_structure.get("beats", [])))
        return ctx
