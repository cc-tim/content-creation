from __future__ import annotations

import json
from typing import Any

import anthropic
import structlog

from pipeline.config import PipelineConfig
from pipeline.knowledge import Knowledge
from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


def get_anthropic_client() -> anthropic.Anthropic:
    """Create Anthropic client from config."""
    config = PipelineConfig()
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


_SENTENCE_ENDINGS = frozenset([".", "?", "!", "…"])  # . ? ! …


def _format_timestamped_transcript(transcript_data: list[dict[str, Any]]) -> str:
    """Format structured transcript as [start–end] text, merging mid-sentence splits."""
    merged: list[str] = []
    buf_text: list[str] = []
    buf_start: float | None = None
    buf_end: float = 0.0

    for entry in transcript_data:
        text = entry.get("text", "").strip()
        if not text:
            continue
        start = float(entry["start"])
        end = start + float(entry.get("duration", 0.0))

        if buf_start is None:
            buf_start = start
        buf_text.append(text)
        buf_end = end

        if text[-1] in _SENTENCE_ENDINGS:
            merged.append(f"[{buf_start:.2f}s–{buf_end:.2f}s] {' '.join(buf_text)}")
            buf_text = []
            buf_start = None

    if buf_text and buf_start is not None:
        merged.append(f"[{buf_start:.2f}s–{buf_end:.2f}s] {' '.join(buf_text)}")

    return "\n".join(merged)


def build_analysis_prompt(
    transcript: str,
    source_url: str,
    title: str,
    transcript_data: list[dict[str, Any]] | None = None,
) -> str:
    """Build the Claude prompt for knowledge extraction."""
    if transcript_data is not None:
        transcript_body = _format_timestamped_transcript(transcript_data)
        transcript_label = "TRANSCRIPT (with source timestamps in seconds):"
    else:
        transcript_body = transcript
        transcript_label = "TRANSCRIPT:"

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

{transcript_label}
{transcript_body}"""


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

        # Load structured transcript if available (gives Claude precise timestamps)
        transcript_data: list[dict[str, Any]] | None = None
        if ctx.transcript_path and ctx.transcript_path.exists():
            try:
                raw = json.loads(ctx.transcript_path.read_text(encoding="utf-8"))
                if raw and isinstance(raw[0], dict) and "start" in raw[0]:
                    transcript_data = [e for e in raw if e.get("text", "").strip()]
            except (json.JSONDecodeError, IndexError, KeyError):
                pass

        prompt = build_analysis_prompt(
            ctx.transcript_text,
            ctx.source_url,
            getattr(ctx, "source_title", "Untitled"),
            transcript_data=transcript_data,
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
        knowledge = Knowledge.from_dict(
            {
                "meta": {
                    "source_type": "youtube",
                    "source_url": ctx.source_url,
                    "title": getattr(ctx, "source_title", "Untitled"),
                    "locale": ctx.locale,
                    "created_at": "",
                    "updated_at": "",
                },
                **result,
            }
        )

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
                {"name": e.name, "role": e.role, "details": e.details} for e in knowledge.entities
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
