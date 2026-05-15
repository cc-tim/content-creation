from __future__ import annotations

import json

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.analyze import get_anthropic_client
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.storyboard import Scene, Storyboard

logger = structlog.get_logger()

LOCALE_INSTRUCTIONS = {
    "zh-TW": (
        "Write in Traditional Chinese (zh-TW), Taiwan usage conventions. "
        "Explain US-specific context (legal system, geography, policing norms) "
        "that Taiwanese audiences need. Use conversational but authoritative tone."
    ),
    "en": "Write in clear, conversational English for a US/international audience.",
    "ja": (
        "Write in Japanese. Use appropriate keigo level for documentary narration. "
        "Add cultural context bridging US and Japanese norms."
    ),
    "es-MX": (
        "Write in Latin American Spanish (Mexican variant). "
        "Explain US cultural context for Latin American audiences."
    ),
}


def build_scriptwrite_prompt(scenes: list[Scene], locale: str) -> str:
    """Build the Claude prompt that writes narration for every beat in one locale."""
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["en"])
    beat_lines = "\n".join(
        f'{s.id} [{s.section}] (~{s.narration_est_sec:.0f}s): {s.beat}'
        for s in scenes
    )
    return f"""You are a scriptwriter for a YouTube channel. For each scene beat below,
write the narration in the target locale. This is a cultural adaptation, NOT a
translation — give the narration the locale's own voice and idiom while hitting the
beat's intent.

LOCALE: {locale}
LANGUAGE INSTRUCTION: {locale_instruction}

RULES:
- Each scene's narration must fit its duration budget (the ~Ns hint). Stay close to it.
- Hit the beat's intent; do not invent new story facts.
- Plain narration text only — no markers, no meta-commentary.

SCENE BEATS:
{beat_lines}

Return ONLY valid JSON mapping scene id to narration string, e.g.
{{"s1": "...", "s2": "..."}}"""


def _write_narration_for_locale(scenes: list[Scene], locale: str) -> dict[str, str]:
    """One Claude call: narration for every scene in one locale. Returns id -> text."""
    client = get_anthropic_client()
    config = PipelineConfig()
    prompt = build_scriptwrite_prompt(scenes, locale)
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


class ScriptwriteStage(PipelineStage):
    @property
    def name(self) -> str:
        return "scriptwrite"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.storyboard_path or not ctx.storyboard_path.exists():
            raise ValueError("No storyboard — run direct stage first")

        logger.info("scriptwrite.start", locale=ctx.locale,
                    secondary=ctx.secondary_locale)

        storyboard = Storyboard.load(ctx.storyboard_path)
        locales: list[str] = [ctx.locale]
        if ctx.secondary_locale and ctx.secondary_locale not in locales:
            locales.append(ctx.secondary_locale)

        for locale in locales:
            narration_by_id = _write_narration_for_locale(storyboard.scenes, locale)
            for scene in storyboard.scenes:
                text = narration_by_id.get(scene.id, "")
                if locale == storyboard.primary_locale:
                    scene.narration = text
                else:
                    scene.narration_alt[locale] = text
            logger.info("scriptwrite.locale_done", locale=locale,
                        scenes=len(storyboard.scenes))

        storyboard.save(ctx.storyboard_path)

        # Derive the primary-locale script for downstream TTS.
        script_dir = ctx.work_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"script_{ctx.locale}.md"
        script_path.write_text(storyboard.derive_script(), encoding="utf-8")
        ctx.script_path = script_path

        logger.info("scriptwrite.complete", locales=locales)
        return ctx
