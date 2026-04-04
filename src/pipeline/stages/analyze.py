from __future__ import annotations

import json

import structlog

from pipeline.config import PipelineConfig
from pipeline.knowledge import Knowledge
from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


def get_anthropic_client():
    """Create Anthropic client from config."""
    import anthropic
    config = PipelineConfig()
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def build_analysis_prompt(transcript: str, source_url: str, title: str) -> str:
    """Build the Claude prompt for knowledge extraction."""
    return f"""Analyze this video transcript and extract structured knowledge.

Extract:
1. **Facts**: Individual factual statements with timestamps. Each gets a unique ID (f1, f2, ...).
   Tag each fact with relevant topics (e.g. "crime", "chase", "legal", "geography").
2. **Entities**: People, organizations, locations mentioned. Each gets a unique ID (e1, e2, ...).
3. **Timeline**: Key events in chronological order, referencing fact IDs.
4. **Context bridges**: Cultural context a non-US audience would need explained.

Return ONLY valid JSON:
{{
  "facts": [
    {{"id": "f1", "text": "factual statement", "timestamp": "M:SS",
      "source": "transcript", "verified": false,
      "tags": ["tag1", "tag2"]}}
  ],
  "entities": [
    {{"id": "e1", "name": "Name", "role": "role description", "details": ""}}
  ],
  "timeline": [
    {{"time": "M:SS", "event": "what happened", "facts": ["f1"]}}
  ],
  "context_bridges": [
    "Cultural context statement"
  ]
}}

SOURCE: {source_url}
TITLE: {title}

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
        prompt = build_analysis_prompt(
            ctx.transcript_text,
            ctx.source_url,
            getattr(ctx, "source_title", "Untitled"),
        )

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(raw_text)

        # Build Knowledge object
        knowledge = Knowledge.from_dict({
            "meta": {
                "source_type": "youtube",
                "source_url": ctx.source_url,
                "title": getattr(ctx, "source_title", "Untitled"),
                "locale": ctx.locale,
                "created_at": "",
                "updated_at": "",
            },
            **result,
        })

        # Save knowledge.json
        knowledge_path = ctx.work_dir / "knowledge.json"
        knowledge.save(knowledge_path)
        ctx.knowledge_path = knowledge_path

        # Backwards compat: populate old fields for existing compose stage
        ctx.story_structure = {
            "beats": [
                {"timestamp": t.time, "beat": "event", "description": t.event}
                for t in knowledge.timeline
            ],
        }
        ctx.knowledge_graph = {
            "entities": [
                {"name": e.name, "role": e.role, "details": e.details}
                for e in knowledge.entities
            ],
            "context_needed_for_target_audience": knowledge.context_bridges,
        }
        ctx.clip_timestamps = []

        logger.info(
            "analyze.complete",
            facts=len(knowledge.facts),
            entities=len(knowledge.entities),
        )
        return ctx
