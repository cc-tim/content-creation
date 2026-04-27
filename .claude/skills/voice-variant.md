---
name: voice-variant
description: Use when the user wants to build a variant of an existing project with a different TTS voice, try a custom voice on a produced project, or promote/discard a voice variant. Triggers: "try X voice on project Y", "build a tim-zhtw-fish version", "make a voice variant", "promote the voice variant", "delete the voice variant".
---

# Voice Variant

Build, compare, and decide on voice variants of produced projects.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id> <voice-id>`, `promote <variant-dir>`, `delete <variant-dir>`, or infer from conversation context.

---

## Autonomy contract

Once the user states their intent (build / promote / delete), execute the full chain automatically — no mid-chain confirmations.

Gates where you pause:
1. Confirming project-id and voice-id before building (if not clear from context)
2. After render: showing the P/D/K prompt
3. After Promote: "Delete variant?" (ask once, then act)
4. Unexpected failure

---

## Step 1 — Resolve project and voice

From conversation context, determine:
- `--from-project` — the parent project ID (integer)
- `--voice` — the voice profile ID (e.g. `tim-zhtw-fish`)

If either is ambiguous, ask once before proceeding. Check variant dir doesn't already exist:

```bash
ls output/projects/ | grep "^{from_project}_"
```

If it exists and `--force` is not intended, ask the user: "Variant `{parent}_{voice}` already exists — overwrite with `--force`, or work with the existing one?"

---

## Step 2 — Build the variant

```bash
uv run pipeline compose voice-variant \
    --from-project <from_project> \
    --voice <voice_id>
```

This runs TTS + Compose automatically. Wait for it to complete (may take several minutes for FishAudio voices).

---

## Step 3 — Post-render decision

After the command prints the soft prompt, relay it to the user:

```
Voice variant ready:
  output/projects/{parent}_{voice}/compose/final_zh-TW_subtitles_no_overlay.mp4

Make {voice} the permanent voice for project {parent}?
  [P] Promote  — copy audio to original, reburn (fast, no scene re-render)
  [D] Delete   — discard this variant, keep original as-is
  [K] Keep both — decide later
```

Wait for the user's choice. The CLI itself also prompts interactively — if running in a terminal, the CLI handles it directly. When invoked non-interactively (e.g. via this skill), relay the prompt yourself and act on the response.

---

## Step 4 — Act on choice (no further prompts)

### P — Promote

```bash
uv run pipeline compose promote-voice --from-project {parent}_{voice}
```

After promote completes, ask once: "Delete the variant directory `{parent}_{voice}`? [y/N]"
Then act immediately.

### D — Delete

```bash
rm -rf output/projects/{parent}_{voice}/
```

Confirm deletion to the user.

### K — Keep both

Remind the user of the promote command for later:

```
Both projects kept. Original project {parent} is still the default for publish.
To promote later: uv run pipeline compose promote-voice --from-project {parent}_{voice}
```

---

## Rebuild decision tree

```
User: "try tim-zhtw-fish on project 1776997800"
  ↓
Resolve project-id + voice-id
  ↓
Check variant dir doesn't already exist
  ↓
Run: pipeline compose voice-variant --from-project 1776997800 --voice tim-zhtw-fish
  ↓
[Render completes]
  ↓
Show P/D/K prompt — wait for user
  ↓
P → promote-voice → ask delete once → act
D → rm -rf variant dir
K → print keep-both message, done
```
