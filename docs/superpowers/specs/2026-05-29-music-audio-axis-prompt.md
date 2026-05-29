# Music on the Audio Axis — paste-ready build prompt

> **✅ COMPLETED (2026-05-29).** This build-prompt has been turned into a full design
> spec: **[`2026-05-29-music-audio-axis-design.md`](2026-05-29-music-audio-axis-design.md)**.
> The four open questions are resolved there (per-scene `music_mood` with a 5-mood
> palette; concrete duck params; one bed per mood; `none`/theme-default for silence).
> The text below is kept as the origin/context record.

---

This is a self-contained brief for a **fresh session**. Paste the "PROMPT" block
below to start. The context above it explains why and what already exists.

---

## Why this exists

The content-creation pipeline produces narrated explainer videos. Today the audio
is **narration only** — there is no background music in the main video. The user
wants a music layer that follows the emotional arc of the story (e.g. tense/dark
under a "disaster" beat, hopeful/resolving under a "things get better" beat),
ducked under the narration so speech stays clear.

This was deferred out of a quality-pass session (2026-05-29) and scoped as its own
feature on the **audio axis**.

## Current state (verified 2026-05-29)

- **No music support in the main pipeline.** Only `src/pipeline/outro/builder.py`
  references music, and that is for outro clips only. `src/pipeline/storyboard.py`
  (`Theme`, `Scene`) has **no** music fields.
- **Audio architecture:** TTS (`src/pipeline/stages/tts.py`) synthesizes one mp3
  per scene (`segment_timings[i].path`), concatenates them into
  `audio/narration_<locale>.mp3`, and builds the SRT. In compose
  (`src/pipeline/stages/compose.py` ~line 705-721) **each scene clip embeds its own
  per-scene segment audio**; the final video is the concatenation of those clips.
  The global `narration_path` is not re-muxed over the final.
- **`scenes.json` is now accurate** (same session fixed it): compose derives scene
  start/duration from the *actual* concatenated clip durations
  (`ComposeStage._write_scenes_json`). This is the reliable timing map for aligning
  music cues to scenes.
- **Budget:** $50/month for all paid APIs — music tracks must come from
  **free / license-clear** sources (e.g. YouTube Audio Library).

## Recommended design (the fresh session should confirm via brainstorming first)

1. **Schema (audio axis):** add an optional per-scene `music_mood` string on
   `Scene` (e.g. `"tense"`, `"hopeful"`, `"neutral"`, `""`=inherit), plus an
   optional `theme.music_default_mood`. A cue starts wherever `music_mood` changes
   between consecutive scenes. Keep it minimal — one mood tag per scene, not a full
   track-editing DSL (YAGNI).
2. **Track library:** a small set of free, license-clear beds under
   `assets/music/<mood>/*.mp3` (YouTube Audio Library). A `mood → track` mapping
   config picks one bed per mood. Cache + credit-tracking like other assets.
3. **Mix (global, not per-clip):** because scene clips already embed narration,
   mix music **over the final concatenated video's audio**, not into each clip.
   Build a full-length bed by concatenating/crossfading the mood beds at cue
   boundaries (boundaries come from the accurate `scenes.json`), then **sidechain-
   duck** it under the narration track (ffmpeg `sidechaincompress`, music ~-12 to
   -15 dB under speech, recovering in pauses), then `amix` with the narration.
4. **CLI surface:** `pipeline compose music --project-id <ID>` that (re)builds the
   mixed audio track and re-muxes it onto the existing final video **without
   re-rendering scenes** (fast iteration, like `reburn`).
5. **First test target — baby-walker `20260504-115232-baby-walker-story`,**
   the s19→s23 arc:
   - **dark / tense** under s19–s20 (the injury mechanisms + the undercount — the
     "it's worse than the numbers say" beat),
   - **crossfade to hopeful / resolving** from s22 (a researcher sounds the alarm)
     into s23 (the decline curve — regulation actually worked).
   (Note: the old s21 emphasis slide was cut in the 2026-05-29 pass; the arc is now
   s19/s20 dark → s22/s23 hopeful.)

## Open questions for the fresh session to resolve

- Per-scene `music_mood` vs a section-level mood map — which granularity?
- Duck depth and attack/release that keep zh-TW narration fully intelligible.
- One bed per mood vs a small rotating pool to avoid repetition on long videos.
- Where music should be silent entirely (e.g. the hook, or the outro which already
  has its own music).

---

## PROMPT (paste this into a fresh session)

> Build a **background-music layer on the audio axis** for the content-creation
> video pipeline. Today there is no music in the main video (only outros have it);
> narration is the only audio, and each scene clip embeds its own narration segment
> (see `src/pipeline/stages/compose.py` ~line 705 and `src/pipeline/stages/tts.py`).
> `compose/scenes.json` now holds accurate per-scene start/duration
> (`ComposeStage._write_scenes_json`) — use it to align music cues.
>
> Goal: lay a royalty-free music bed under the narration that follows the story's
> emotional arc, sidechain-ducked so speech stays clear. Constraint: free /
> license-clear tracks only (YouTube Audio Library), $50/mo budget.
>
> Start with the brainstorming skill to confirm the design, then implement:
> 1) a minimal schema for mood (per-scene `music_mood` + theme default);
> 2) a `mood → free track` library under `assets/music/`;
> 3) a **global** mix step (music is mixed over the final concatenated audio, NOT
>    per-clip): build a full-length bed crossfading mood beds at cue boundaries
>    (from scenes.json), sidechain-duck under narration (~-12..-15 dB), `amix`;
> 4) a `pipeline compose music --project-id <ID>` subcommand that rebuilds the
>    mixed track and re-muxes onto the existing final video without re-rendering
>    scenes.
>
> First test target: project `20260504-115232-baby-walker-story`, the s19→s23 arc —
> dark/tense under s19–s20 (injury mechanisms + undercount), crossfading to
> hopeful/resolving from s22 (researcher sounds the alarm) into s23 (decline curve;
> regulation worked). Verify the narration stays fully intelligible under the bed.
