# Voice Recommendation Feature — Design Spec

**Date:** 2026-04-28
**Status:** Approved

## Problem

Voice choice currently requires the producer to know the voice registry by heart and manually reason about content fit. A wrong voice (wrong register, wrong pace) produces a video that feels emotionally off — and is only discovered after TTS and compose have already run. The recommendation system surfaces this decision earlier, with reasoning, before any API credits are spent on synthesis.

---

## Decisions

| Question | Decision |
|---|---|
| When does it run? | End of `DirectStage` — storyboard + script exist, TTS hasn't started |
| Where is it surfaced? | Review gate (same location as proofread + storytell) |
| With `--skip-review`? | Auto-applies top-ranked voice; logs choice to sessions.json |
| Data sources | `voices/registry.json` meta + storyboard content signals |
| Override mechanism | User types a different voice ID at the prompt, or passes `--voice` flag (which skips the prompt entirely) |
| New context field? | Yes — `voice_recommendation: dict | None` stores ranked result for logging |

---

## Architecture

### New file: `src/pipeline/voices/recommender.py`

Single public function:

```python
def recommend_voice(
    storyboard: Storyboard,
    locale: str,
    registry: VoiceRegistry,
    current_voice_id: str | None,
) -> VoiceRecommendation
```

Returns a `VoiceRecommendation` dataclass:

```python
@dataclass
class VoiceRecommendation:
    ranked: list[VoiceScore]   # best first
    signals: ContentSignals    # what was detected in the storyboard

@dataclass
class ContentSignals:
    register: str              # "warm" | "neutral" | "formal" | "urgent"
    avg_scene_sec: float
    content_type: str          # niche label or inferred from storyboard sections

@dataclass
class VoiceScore:
    voice_id: str
    display_name: str
    score: int
    verdict: str               # "✓ recommended" | "~" | "✗ avoid"
    reason: str                # one-line human-readable explanation
```

### Content signal extraction

Three signals from the storyboard:

**1. Emotional register** — keyword scan across all scene narrations:

| Signal | Keywords (zh-TW focus) | Register |
|---|---|---|
| Warm | 你、孩子、感受、陪、愛、理解、溫柔、父母 | `warm` |
| Urgent/tense | 危險、衝突、逃、死、警察、攻擊、緊急 | `urgent` |
| Clinical/formal | 研究、數據、報告、分析、顯示、根據 | `formal` |
| Default | (none of the above dominate) | `neutral` |

Dominant register = whichever category has the most hits. If warm + urgent are tied, prefer `warm` (more conservative choice).

**2. Avg scene duration** — from `storyboard.scenes[i].narration_est_sec` (pre-TTS) or `segment_timings[i].duration_ms / 1000` (post-TTS if rerunning):

```
avg_scene_sec = sum(narration_est_sec for scene in storyboard.scenes) / len(scenes)
```

**3. Content type** — from `PipelineContext.niche` if set; otherwise inferred from storyboard section distribution:
- > 30% HOOK/CLIMAX scenes → `suspense`
- > 40% CONTEXT/ANALYSIS scenes → `educational`
- Mix with warm register → `parenting` / `psychology`

### Scoring

Each voice in the registry (matching locale) is scored:

```
score = 0
for tag in voice.meta.fits:
    if tag matches content_type or register: score += 1
for tag in voice.meta.avoid:
    if tag matches content_type or register: score -= 2
if voice.meta.pace == "fast" and avg_scene_sec > 18: score -= 1
if voice.meta.emotional_range == "low" and register == "warm": score -= 1
```

Verdict thresholds: score ≥ 2 → `✓`, score 0–1 → `~`, score < 0 → `✗`.

### Integration into DirectStage

At the end of `DirectStage.run()`, after storyboard is saved:

```python
from pipeline.voices.recommender import recommend_voice
rec = recommend_voice(storyboard, ctx.locale, registry, ctx.voice_id)
ctx.voice_recommendation = rec.to_dict()
ctx.save()
```

`voice_id` is NOT changed by DirectStage — the recommendation is stored but not applied. Application happens at the review gate.

### Review gate display (`src/pipeline/cli.py`)

Added to the review gate block (after proofread/storytell output):

```
Voice recommendation for this project:
  Content: parenting / emotional warmth · avg scene 20s · register: warm

  ✓ zh-TW-default-f  (HsiaoChen)    warm · medium pace · fits parenting   ← recommended
  ~ tim-zhtw-fish    (沉稳男声)      fast pace compresses 20s scenes; short template limits warmth
  ✗ zh-TW-default-m  (YunJhe)       neutral register mismatches emotional content

Current voice: zh-TW-default-f  →  Recommended: zh-TW-default-f  (no change)
Use recommended [Y] / enter different voice ID / [s] skip:
```

Two distinct cases at the prompt:

**Recommended = current voice:** prompt says "no change" — Y or Enter is a no-op.

**Recommended ≠ current voice** (e.g. current is `tim-zhtw-fish`, recommended is `zh-TW-default-f`):
```
Current voice: tim-zhtw-fish  →  Recommended: zh-TW-default-f
Switch to recommended [Y] / keep current [k] / enter different voice ID / [s] skip:
```
Y applies the recommended voice. k keeps the current. Entering an ID applies that ID.

In all cases: `ctx.voice_id = <result>; ctx.save()` before TTS.

With `--skip-review`: auto-applies the top-ranked voice and logs `voice_recommendation_applied` to sessions.json.

If `--voice` was passed explicitly on the CLI: skip the recommendation prompt entirely (user already decided).

### PipelineContext addition

One new field in `src/pipeline/stages/base.py`:

```python
voice_recommendation: dict | None = None  # stored result from VoiceRecommender
```

Serialises automatically via existing `to_dict` / `from_dict`.

---

## File Locations

| Action | File |
|---|---|
| Create | `src/pipeline/voices/recommender.py` |
| Modify | `src/pipeline/stages/direct.py` — call recommender, store result in ctx |
| Modify | `src/pipeline/cli.py` — display recommendation at review gate |
| Modify | `src/pipeline/stages/base.py` — add `voice_recommendation` field |
| Test | `tests/unit/test_voice_recommender.py` |

---

## Test Cases

- Warm-register storyboard → HsiaoChen scores highest for zh-TW locale
- Urgent-register storyboard → YunJhe or male neutral voice scores above female warm voice
- Fast voice penalised when avg scene > 18s
- Low emotional_range penalised when register is warm
- Voice with `--voice` flag set → recommender still runs but gate is skipped
- `--skip-review` auto-applies top voice and logs to sessions
- Locale filter: only voices matching ctx.locale are included in ranking
- Edge case: no voices in registry for locale → skip recommendation silently

---

## Out of Scope

- Multi-locale recommendation (recommendation is per-locale, not cross-locale)
- Learning from user overrides (no feedback loop into scoring weights — keep it deterministic)
- Audio preview of candidate voices at the gate
