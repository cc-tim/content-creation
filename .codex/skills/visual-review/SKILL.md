---
name: visual-review
description: Look at the rendered scenes of a project and report visual issues (subtitle/overlay overlap, illegible text, off-screen content, image-narration mismatch, style drift). Use when asked to "review the rendered video", "check for visual issues", "look for layout problems", "did the overlay come out right", or after a render finishes and the user wants a sanity check before publish. Runs entirely inside this Claude Code session — no extra Anthropic API call. Triggers also on phrases like "judge the scene image", "do a visual pass on project X", "spot check the rendered scenes".
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv, ffmpeg]
---

# Visual Review — Look at What Was Actually Rendered

Text-only reviewers (`proofread`, `storytell`) check the script. They cannot
catch layout bugs (rich_slide text vs. burned subtitle stacking on top of each
other), illegible micro-text, off-canvas content, or image-narration
contradictions. **This skill is the only one that actually looks at the frames.**

It runs in the assistant's own context — **no separate Claude API call, no
billing on the project's API key**. The Python helper just extracts frames;
the model judging them is *you*.

---

## Step 1 — Extract midpoint frames (one per scene)

```bash
cd /home/tim-huang/content-creation
uv run pipeline visual-review extract-frames --project-id <ID>
```

Frames go to `output/projects/<ID>/compose/scenes/_review_frames/<scene_id>.png`.
The CLI prints a table mapping each frame to its scene's narration + overlay.

---

## Step 2 — Decide: inline read, or dispatch a subagent?

**Inline (≤ 12 scenes):** read each frame directly in this conversation.

**Subagent (> 12 scenes, or you want to keep main context light):** invoke
`superpowers:dispatching-parallel-agents` with a chunked plan, OR call the
`Agent` tool once with `subagent_type=general-purpose`. Pass the agent the
review rubric (below) and the absolute frame paths. The subagent reads the
frames, returns a structured issue list, and the main session stays clean.

Either way — do not call the Anthropic API directly from Python; the in-session
read covers it.

---

## Step 3 — The review rubric

For each frame, check in this priority order:

1. **Text/overlay overlap** — subtitle line and any overlay text are stacking
   on each other or sharing the same y-band. (rich_slide is the most common
   offender — known issue.)
2. **Off-canvas / cropped text** — overlay or subtitle clipping at any edge,
   or text running off the safe area.
3. **Illegibility** — font too small for the visual density, low contrast
   against the background, color clash that hurts readability.
4. **Image vs. narration mismatch** — picture says one thing, the narration
   for that scene says another. (e.g. narration mentions "夜晚" but the
   frame is daytime.)
5. **Style drift** — one scene's color grading, character look, or render
   style breaks markedly from its neighbors.
6. **Subject occluded** — important detail (face, key prop) is covered by
   the subtitle or overlay box.

Severity:
- **MAJOR** — affects watchability (overlap, illegible, mismatched, occluded subject)
- **MINOR** — visible but not blocking (mild style drift, optional improvement)

---

## Step 4 — Report format

Match the proofread/storytell format so the same table renderer works:

```
ISSUE|<scene_id>|MAJOR or MINOR|觀察到的現象|建議的修正方向|原因
```

If no issues: just say `OK`.

Do **not** auto-apply fixes. Visual changes always need human action — the
fix path is to edit the storyboard's `visual.prompt`, theme, or overlay
positioning, then `compose rescene --scene <id>`.

---

## Step 5 — Hand off to scene-update for the fixes

For each MAJOR issue you flagged:

1. State the scene + observation + suggested change.
2. Wait for user approval.
3. Then invoke the `scene-update` skill — it handles the storyboard edit +
   targeted rescene chain. Do NOT brute-force a rebuild of all scenes.

---

## Cost note

This skill is free in the sense that no extra Anthropic billing happens — the
vision pass is part of the running Claude Code session. The only cost is
time: extracting 24 frames takes ~5–15 seconds; reading them in-context adds
some token budget but no per-call API spend.
