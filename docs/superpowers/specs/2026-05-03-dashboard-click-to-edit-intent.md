---
title: Dashboard Click-to-Edit (Intent / Pre-Spec)
date: 2026-05-03
status: requirements-only
related: 2026-05-03-wiki-explainer-to-video-bridge-design.md
---

# Dashboard Click-to-Edit — Intent Brief

This is a **requirements-only** brief, not a design. The user (Tim) will
spin up a dedicated session to brainstorm and design this. This file is the
handoff so that session has full context.

## Pain point (in the user's words, paraphrased)

> Currently there are some narration / subtitle / image elements on the
> dashboard I would like to fix, but I need to remember the scene ID. If we
> had a chat interface, and what I click in the UI could click and add a
> tag like `@sceneXX/footage` or `@sceneYY/subtitle`, then I'd say what I
> want for each, and submitting would trigger something like `claude -p ...`
> to do the work. Maybe a hook notifies me when done and refreshes the
> dashboard.

## Requirements

1. **Clickable elements** on the dashboard's per-project view, including:
   - Scene visual (image / clip)
   - Subtitle line
   - Overlay text
   - Narration audio segment
2. **Click → token insertion** into a chat input box. Tokens use a stable
   addressable form: `@s9/visual`, `@s9/subtitle`, `@s9/overlay`,
   `@s9/narration` (scene id + element type).
3. **User types natural-language requirement** after the token(s).
4. **Submit kicks off agent execution** that performs the requested edit
   (e.g. via `claude -p` subprocess, or a queued worker, or another
   mechanism — see categories below).
5. **Completion notification** — desktop notify, dashboard banner, or push.
6. **Dashboard auto-refresh** when the project's artifacts change so the
   user immediately sees the result of an applied edit.

## Categories the design must address

These came up during the scenario-2 scoping in the brainstorm session
(2026-05-03). Each is a real design decision the next session needs to
work through.

1. **Selector mapping.** How does a click on a rendered video frame /
   image / subtitle line translate to a stable scene + element identifier?
   Particularly hard: clicking *inside a video player* and resolving to a
   specific scene (probably needs scene-time markers in the player). Easier:
   clicking on the per-scene panel that already exists on the dashboard.

2. **Agent runtime.** Where does the agent actually run?
   - Subprocess (`claude -p ...`) launched directly from the dashboard
     backend? Simple but ties dashboard lifetime to agent lifetime.
   - Queued task processed by a worker? More robust, survives reload.
   - Sandboxed? (Should an edit-agent be allowed to touch any file in
     the project, or just `output/projects/<id>/storyboard.json` and
     `compose/`?)

3. **Progress visibility.** Streaming output from the agent back to the
   chat box; an in-flight indicator; ability to see / cancel running
   tasks. SSE? Websocket? Polling?

4. **Notify + refresh round-trip.** Completion fires:
   - Hook? Desktop notification? OS-level (libnotify)?
   - Push to the dashboard? (Websocket / SSE.)
   - Polling refresh? (Simpler, less responsive.)

5. **Failure handling.** Agent errors mid-edit. Partial successes
   (e.g. storyboard updated but compose failed). What surfaces in the
   chat box. Retry affordance.

6. **Concurrency.** Two edit requests submitted at once:
   - Queue serially?
   - Reject second until first finishes?
   - Allow parallel if they touch different scenes?

7. **Edit semantics.** What CAN the agent change?
   - Subtitle text → simple, edits storyboard, requires recompose
   - Overlay text → simple, edits storyboard, requires recompose
   - Image regen → expensive (API call), needs prompt + tier choice
   - Clip swap → maybe surface a UI for source / time selection
   - Narration → re-TTS that scene; pacing concerns; voice consistency
   Some may need their own UI step before submission.

8. **Trust boundary.** The agent runs LLM-driven edits. How does the user
   verify the change is what they wanted before it's committed/visible?
   Diff view? Preview render? "Approve" button?

## Relationship to scenario 1

Scenario 1 (wiki explainer → video bridge) and scenario 2 are independently
designable and buildable. They share the dashboard surface, so the verifier
view from scenario 1 and the click-to-edit interactions from scenario 2
should eventually share interaction conventions (same click selectors, same
refresh mechanism). When designing scenario 2, check what scenario 1's
verifier ends up using and align.

## Suggested next-session opener

> *"Read `docs/superpowers/specs/2026-05-03-dashboard-click-to-edit-intent.md`
> for context. Brainstorm the design for the click-to-edit dashboard
> editor — start by walking through the 8 categories listed there one at
> a time, lightest first."*

The brainstorming skill should drive that session through the standard
flow (clarifying questions one at a time → 2-3 approaches → design →
spec).
