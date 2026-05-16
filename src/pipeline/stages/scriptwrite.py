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


def _english_word_budget_for_zhtw(zhtw_text: str) -> int:
    """Empirical conversion: Mandarin chars × 0.55 ≈ English words for similar duration.

    Counts only CJK chars (ignores Latin loanwords, digits, punctuation) so a
    line like "在 1901 年" gets a budget driven by the meaningful Mandarin
    content, not the digits that read fast in either language.
    """
    cjk_chars = sum(1 for ch in zhtw_text if "㐀" <= ch <= "鿿")
    return max(3, round(cjk_chars * 0.55))


def _build_mla_discipline_block(
    scenes: list[Scene], primary_narrations: dict[str, str], primary_locale: str
) -> str:
    """Per-scene EN word budgets so the alt track fits within the MLA drift gate.

    Without this guidance, models tend to write 1.5–2× the word count that the
    primary locale's audio duration can hold — the MLA drift gate then fails
    and a manual `pipeline mla rebalance` is needed to recover. The 0.55
    char→word factor is calibrated for zh-TW → en-US (Mandarin packs ~1.4×
    the info density per char as English does per word).
    """
    budget_lines = []
    for s in scenes:
        primary = primary_narrations.get(s.id, "")
        if not primary:
            continue
        chars = sum(1 for ch in primary if "㐀" <= ch <= "鿿")
        target = _english_word_budget_for_zhtw(primary)
        budget_lines.append(
            f"  {s.id}: ~{target} words  ({chars} {primary_locale} chars × 0.55)"
        )
    if not budget_lines:
        return ""
    budgets = "\n".join(budget_lines)
    return f"""

MLA / LENGTH DISCIPLINE (CRITICAL — read before writing):
This English track will be synthesized as TTS audio that must align with the
{primary_locale} track. The English audio for each scene must fit within
±10% of the {primary_locale} audio duration.

Practical rule: {primary_locale} packs ~1.4× the info per character that
English packs per word. So target_english_words ≈ {primary_locale}_char_count × 0.55.

Per-scene budgets (target_words computed for you — match within ±2):
{budgets}

If meaning truly requires more words, COMPRESS: drop articles, use shorter
synonyms, cut hedges. Keep names, numbers, dates, and quoted phrases verbatim.
NEVER exceed: english_words > {primary_locale}_chars × 0.75 — above this,
the audio is statistically guaranteed to overshoot the {primary_locale} track.
"""


def build_scriptwrite_prompt(
    scenes: list[Scene],
    locale: str,
    *,
    primary_narrations: dict[str, str] | None = None,
    primary_locale: str | None = None,
) -> str:
    """Build the Claude prompt that writes narration for every beat in one locale.

    When `primary_narrations` is provided (i.e., this is a secondary-locale pass
    on a MLA project), the prompt is extended with per-scene length budgets so
    the alt track lands within the MLA drift tolerance from the get-go.
    """
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["en"])
    beat_lines = "\n".join(
        f'{s.id} [{s.section}] (~{s.narration_est_sec:.0f}s): {s.beat}'
        for s in scenes
    )
    mla_block = ""
    if primary_narrations and primary_locale and locale != primary_locale:
        mla_block = _build_mla_discipline_block(
            scenes, primary_narrations, primary_locale
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
{mla_block}
SCENE BEATS:
{beat_lines}

Return ONLY valid JSON mapping scene id to narration string, e.g.
{{"s1": "...", "s2": "..."}}"""


def _write_narration_for_locale(
    scenes: list[Scene],
    locale: str,
    *,
    primary_narrations: dict[str, str] | None = None,
    primary_locale: str | None = None,
) -> dict[str, str]:
    """One Claude call: narration for every scene in one locale. Returns id -> text.

    When `primary_narrations` is given (secondary-locale pass), the prompt
    includes per-scene length budgets so the alt track fits the MLA gate.
    """
    client = get_anthropic_client()
    config = PipelineConfig()
    prompt = build_scriptwrite_prompt(
        scenes, locale,
        primary_narrations=primary_narrations,
        primary_locale=primary_locale,
    )
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"scriptwrite: Claude returned non-JSON for locale {locale!r}: {e}\nRaw: {raw[:200]}"
        ) from e


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
            primary_narrations = None
            if locale != storyboard.primary_locale:
                # Secondary-locale pass: feed the now-written primary narration
                # into the prompt so per-scene EN word budgets are correct.
                primary_narrations = {s.id: s.narration for s in storyboard.scenes}
            narration_by_id = _write_narration_for_locale(
                storyboard.scenes, locale,
                primary_narrations=primary_narrations,
                primary_locale=storyboard.primary_locale,
            )
            for scene in storyboard.scenes:
                text = narration_by_id.get(scene.id, "")
                if scene.id not in narration_by_id:
                    logger.warning("scriptwrite.missing_scene", scene_id=scene.id, locale=locale)
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
        script_path.write_text(storyboard.derive_script(locale=ctx.locale), encoding="utf-8")
        ctx.script_path = script_path

        logger.info("scriptwrite.complete", locales=locales)
        return ctx
