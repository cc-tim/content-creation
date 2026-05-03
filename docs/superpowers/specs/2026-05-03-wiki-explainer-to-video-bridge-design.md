---
title: Wiki Explainer → Video Bridge
date: 2026-05-03
status: design
---

# Wiki Explainer → Video Bridge

## Goal

Bridge `know-fountains` wiki explainers into the `content-creation` video
production pipeline so that:

1. **The explainer's frontmatter IS the production manifest.** Materials and
   directorial intent are authored *in* the wiki page during normal wiki
   work, not extracted post-hoc.
2. **Wiki authoring becomes video-aware** when an explainer has
   `intent: video`. Any addition (image, quote, fact) prompts a shaping
   question and updates the right frontmatter block.
3. **A dashboard verifier** shows materials ↔ rendered video side by side,
   so the user can see what was kept, modified, dropped, or missing —
   with **drops as a first-class user choice**, not a failure.

## Non-goals

- Click-to-edit dashboard. See companion brief
  `2026-05-03-dashboard-click-to-edit-intent.md` (scenario 2, future session).
- Extracting manifests via a separate API call. The in-session assistant
  does the work — no extra API budget.
- Auto-publish driven by verifier pass.
- Multi-explainer-per-video projects.

## Architecture

```
~/know-fountains/                         ~/content-creation/
  wiki/<domain>/explainers/                 src/pipeline/...
    baby-walker-story.md                    output/projects/<id>/
      frontmatter = MANIFEST                  source/explainer.md (copy)
                                              storyboard.json
                                              compose/final_*.mp4
  raw/<domain>/<slug>/assets/         ───→  consumed as scene visuals
    images/clips/...

  .claude/skills/                         skills/produce/SKILL.md
    video-intent-authoring/SKILL.md         (extended: URL OR explainer path)
                                          src/pipeline/dashboard/
                                            verifier view (new)
  .claude/settings.json                   .claude/settings.json
    additionalDirectories:                  additionalDirectories:
      ["~/content-creation"]                  ["~/know-fountains"]
```

Two projects, permanently cross-linked. Manifest lives **inside** the
explainer's frontmatter. Single source of truth, human- and machine-readable.

## The manifest (extension to wiki frontmatter)

When `intent: video` is set on a wiki page, these blocks become meaningful:

```yaml
---
title: "Baby Walkers..."
type: explainer
domain: parenting
tags: [baby-walker, history, safety]
sources: ["[[baby-walker-wikipedia]]"]
created: 2026-05-03
updated: 2026-05-03

# ↓ video-intent fields ↓
intent: video
video_brief: |
  History piece. First half (1440 → 1990) uses page-turn transitions
  between scenes. Intro should feel like something the host randomly
  encountered IRL or online — found-photograph energy, not a thesis
  opener. Don't moralize about parenting choices.

verbatim_lines:
  - "I don't think this idea of a baby-walker took off"
  - "Wheels + suspended seat = the one to avoid"

key_facts:
  - "ER visits dropped 90% from 1990 to 2014"
  - "230,676 US children injured over 25 years"

required_images:
  - path: raw/parenting/baby-walker/assets/Jesus_in_a_baby_walker_...jpg
    role: intro_candidate
    caption: "Jesus in a baby walker, Hours of Catherine of Cleves, c. 1440"

required_clips: []

required_sequence:
  - "history → stats → regulation → rule"
---
```

All blocks except `intent: video` are optional. An explainer can start with
just `intent: video` and `video_brief`, then grow over many wiki sessions.

### Convention for prose vs frontmatter

- Prose `![](raw/.../foo.jpg)` → image is **considered** for the video.
- Prose `> blockquote` → line is **considered** for verbatim use.
- Frontmatter `required_images` / `verbatim_lines` → promoted to **required**.
- The user weighs the difference. The wiki skill prompts during authoring.

## Components

### A. `know-fountains` — new skill `video-intent-authoring`

Path: `~/know-fountains/.claude/skills/video-intent-authoring/SKILL.md`

**Trigger description (for skill auto-invocation):**

> Use when adding material (images, quotes, facts, structure) to a wiki page
> that has `intent: video` in frontmatter. Asks the video-shaping question
> for each addition and keeps prose + frontmatter manifest blocks in sync.

**Behaviors:**

| User says... | Skill asks / does |
|---|---|
| *"add this image"* | adds `![](raw/...)` link in prose; asks: required for video? role hint? → updates `required_images` |
| *"keep this quote"* | adds `> blockquote` in prose; asks: verbatim or paraphrasable? → updates `verbatim_lines` or `key_facts` |
| *"this fact matters"* | inline-bolds in prose; updates `key_facts` |
| *"open with this"* / *"end with this"* | adds note to `video_brief`; sets image role if relevant |
| *"first half should..."* | appends to `video_brief` |

The skill also keeps `updated:` frontmatter fresh.

### B. `content-creation` — extend the `produce` skill

Branch on the input type:

```
produce <input>
  ├── if input is YouTube URL → existing flow unchanged
  └── if input is path to .md  → new branch:
        1. Read explainer + frontmatter manifest
        2. Copy explainer.md to output/projects/<id>/source/explainer.md
        3. Run interactive manifest review (in chat, no API)
        4. Continue to storyboard generation, with manifest as hard input
        5. TTS, compose, etc. — unchanged
```

**Manifest review questions** the assistant raises before storyboard:

- Required images with no role hint → ask role
- `verbatim_lines` longer than ~25 words → flag (breaks narration cadence)
- Conflicting `required_sequence` vs prose section order → ask which wins
- Long explainer with no `video_brief` → ask for high-level direction
- Required image with no caption → ask (needed for storyboard scene generation)
- Anything else the assistant finds genuinely unclear

After review, the user has had a chance to revise the manifest. The
explainer.md is updated in `know-fountains/` (since the manifest IS the
explainer's frontmatter), and a copy is taken into `output/projects/<id>/`
for reproducibility.

### C. `content-creation` — dashboard verifier view

New page at `/verify/<project-id>` (or a panel in the existing project view).

**Layout:** two columns.

| Left: manifest checklist | Right: rendered output |
|---|---|
| `video_brief` (text reminder) | Final video player |
| `verbatim_lines` with status badges | Scene strip (s1, s2, ..., sN) |
| `key_facts` with badges | Click a scene → highlight matching items on left |
| `required_images` with badges + thumbnails | |
| `required_clips` with badges | |
| `required_sequence` with badges | |

**Badges per item:**

- ✅ **used** — found verbatim / exact path match in storyboard or render
- ⚠️ **modified** — partial / fuzzy match (key_facts only)
- ❌ **missing** — not found
- ⏸️ **user-skipped** — user clicked "OK to drop" on this item

The `OK to drop` action is reversible (toggle). Skipped items don't count
against the missing-count summary.

**State persistence:** drop decisions stored in
`output/projects/<id>/verifier_state.json` (per-project, gitignored).

### D. Settings cross-link

Both projects' `.claude/settings.json` get an `additionalDirectories` entry
pointing at the other project, so any session in either project sees both
working directories by default.

```jsonc
// ~/content-creation/.claude/settings.json
{
  "additionalDirectories": ["~/know-fountains"]
}
// ~/know-fountains/.claude/settings.json
{
  "additionalDirectories": ["~/content-creation"]
}
```

(Resolved with `~` or absolute paths per the harness's settings rules — to
be confirmed during implementation; may use `update-config` skill.)

## Verifier check rules

| Category | Auto-check rule | Manual fallback |
|---|---|---|
| `required_images` | exact path match in any scene's visual ref | — |
| `required_clips` | exact path match in any scene's visual ref | — |
| `verbatim_lines` | exact string match in narration / subtitle / overlay text | — |
| `key_facts` | (v1) flagged for manual review; (later) embedding-based fuzzy match suggests probable hits | user toggles "stated ✓" after watching |
| `required_sequence` | — | user toggles "honored ✓" after watching |
| `video_brief` | — | reminder text shown alongside; no automatic check |

`v1` ships the auto-checks for images / clips / verbatim_lines. Manual
checkboxes for facts / sequence are populated by the user during review.
Later iterations can add semantic matching for facts and prose-order
analysis for sequence.

## Data flow end to end

```
1. AUTHORING (know-fountains, ongoing across sessions)
   User adds wiki material → video-intent-authoring skill runs (when
   intent: video) → updates prose + frontmatter manifest in lockstep.

2. PRODUCE INVOKED (content-creation)
   "produce video for baby-walker" or "/produce <path>"
   → produce skill detects path → branches to explainer-path flow.

3. INTERACTIVE MANIFEST REVIEW (in chat, no extra API)
   Assistant: "I read N verbatim lines, M facts, K images. Brief says
   X. Things I'm unclear on: [list]. Anything to change before storyboard?"
   User edits manifest in chat; assistant writes back to explainer.md.

4. STORYBOARD GENERATION (existing skill, manifest-aware)
   Standard storyboard, but manifest is hard input:
   - required_images placed in scenes (role hints scene placement)
   - verbatim_lines must appear unmodified in narration/subtitle/overlay
   - key_facts must be stated somewhere
   - video_brief shapes pacing / transitions / intro feel

5. RENDER (existing TTS + compose, unchanged)

6. VERIFICATION (dashboard)
   Verifier view reads explainer.md + storyboard.json + render output;
   renders side-by-side checklist with badges.
   User reviews; toggles "OK to drop" on items they're fine releasing.
```

## What does NOT change

- YouTube URL flow in `produce` — same path, just a different branch.
- `analyze` outputs (`knowledge.json`) and `storyboard.json` schema —
  same shape, different inputs at the front.
- TTS, compose, publish — untouched.
- Wiki pages without `intent: video` — wiki skills behave exactly as before.
- The `raw/` directory's immutability rule — never edited by these skills.

## Skill file size watch

The `produce` skill (`skills/produce/SKILL.md`) will grow with the new
explainer-path branch. Heuristic:

- Under ~250 lines after the addition: leave as-is.
- 250–400 lines: consider extracting an `import-explainer` sub-skill.
- Over 400 lines: split.

If a split becomes warranted, dispatch `codex:rescue` to do it as a
follow-up task — the split is mechanical, doesn't need primary attention.

## Open questions / future enhancements

- **Semantic matching for `key_facts`.** v1 is manual-only. Future:
  embeddings or LLM judgment to suggest probable matches in narration,
  reducing the user's manual-check burden.
- **Sequence honoring auto-check.** v1 is manual. Future: compare prose
  section order to scene order automatically and flag mismatches.
- **Multi-explainer projects** (combining two explainers into one video).
  Out of scope for v1.
- **Verifier exports.** A "share verifier state" link could be useful for
  showing reviewers what made it. Out of scope for v1.
- **Drift detection.** If the explainer in `know-fountains` is edited
  *after* `produce` ran, the verifier could flag drift between the
  per-project copy and the canonical wiki version. Out of scope for v1.

## Implementation order (sketch — refined in plan)

1. Settings cross-link (`additionalDirectories` in both projects).
2. `video-intent-authoring` skill in know-fountains.
3. Manifest schema documented in `know-fountains/CLAUDE.md` for reference.
4. `produce` skill: explainer-path branch + interactive review.
5. Storyboard generation: respect manifest as hard input (verify in
   existing skill / extend constraints).
6. Dashboard verifier view: read manifest + storyboard + render; render
   the checklist UI; persist drop decisions.
7. Skill-size check; split `produce` if needed.

The plan that follows this spec will detail each step with concrete file
paths, schemas, and acceptance criteria.
