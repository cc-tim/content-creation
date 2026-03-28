from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.analyze import get_anthropic_client
from pipeline.stages.base import PipelineContext, PipelineStage

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


def build_scriptwrite_prompt(
    story_structure: dict[str, Any],
    knowledge_graph: dict[str, Any],
    locale: str,
) -> str:
    """Build the Claude prompt for script adaptation (NOT translation)."""
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["zh-TW"])

    return f"""You are a scriptwriter for a YouTube channel. Write a NEW, ORIGINAL script
based on the story analysis below. This is NOT a translation — it is a cultural adaptation.
Restructure the narrative for maximum engagement with the target audience.

LOCALE: {locale}
LANGUAGE INSTRUCTION: {locale_instruction}

STORY STRUCTURE:
{json.dumps(story_structure, indent=2, ensure_ascii=False)}

KNOWLEDGE GRAPH:
{json.dumps(knowledge_graph, indent=2, ensure_ascii=False)}

VIDEO STRUCTURE (follow this):
- [HOOK] (0-30s): Start with the most dramatic moment out of context
- [CONTEXT] (30s-2min): Map, people, setting, background
- [RISING] (2-6min): Escalation of events
- [CLIMAX] (6-8min): Peak tension
- [AFTERMATH] (8-10min): Resolution, consequences
- [ANALYSIS] (10-12min): Commentary, broader implications

USE THESE MARKERS in your script:
- [CLIP:MM:SS-MM:SS] — reference a source video segment
- [OVERLAY:map:Location] — map overlay
- [OVERLAY:namecard:Name, Age, Role] — name card
- [OVERLAY:text:Important Info] — text card
- [OVERLAY:title:Title Text] — title card
- [PAUSE:Ns] — dramatic pause (N seconds)

Plain text = narration (will be sent to TTS).

Keep source clips SHORT (5-15 seconds each). Original narration must be 50-70%+ of the video.

Write ONLY the script with markers. No meta-commentary."""


def parse_script_markers(script: str) -> list[dict[str, Any]]:
    """Parse a script into a list of typed markers and narration blocks."""
    markers: list[dict[str, Any]] = []
    lines = script.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Section marker: [HOOK], [CONTEXT], etc.
        if re.match(r"^\[(HOOK|CONTEXT|RISING|CLIMAX|AFTERMATH|ANALYSIS)\]$", stripped):
            markers.append({"type": "section", "value": stripped[1:-1]})
        # Clip reference: [CLIP:MM:SS-MM:SS] (1-2 digit minutes)
        elif re.match(r"^\[CLIP:\d{1,2}:\d{2}-\d{1,2}:\d{2}\]$", stripped):
            times = stripped[6:-1]
            start, end = times.split("-")
            markers.append({"type": "clip", "start": start, "end": end})
        # Overlay: [OVERLAY:type:content]
        elif stripped.startswith("[OVERLAY:"):
            inner = stripped[9:-1]
            overlay_type, content = inner.split(":", 1)
            markers.append({"type": "overlay", "overlay_type": overlay_type, "content": content})
        # Pause: [PAUSE:Ns]
        elif re.match(r"^\[PAUSE:\d+s\]$", stripped):
            seconds = int(stripped[7:-2])
            markers.append({"type": "pause", "seconds": seconds})
        else:
            # Narration text
            markers.append({"type": "narration", "text": stripped})

    return markers


class ScriptwriteStage(PipelineStage):
    @property
    def name(self) -> str:
        return "scriptwrite"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.story_structure or not ctx.knowledge_graph:
            raise ValueError("No analysis available — run analyze stage first")

        logger.info("scriptwrite.start", locale=ctx.locale)

        client = get_anthropic_client()
        config = PipelineConfig()

        prompt = build_scriptwrite_prompt(
            ctx.story_structure, ctx.knowledge_graph, ctx.locale,
        )

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        script_text = response.content[0].text

        # Save script
        script_dir = ctx.work_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"script_{ctx.locale}.md"
        script_path.write_text(script_text, encoding="utf-8")
        ctx.script_path = script_path

        logger.info("scriptwrite.complete", path=str(script_path), chars=len(script_text))
        return ctx
