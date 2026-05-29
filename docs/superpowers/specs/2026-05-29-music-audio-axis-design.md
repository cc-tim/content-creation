# Music on the Audio Axis — Design Spec

**Date:** 2026-05-29
**Status:** Approved (design); implementation pending
**Supersedes:** `2026-05-29-music-audio-axis-prompt.md` (the build-prompt this spec was derived from)

## Goal

Lay a royalty-free **background-music bed** under the narration of the main video,
following the story's emotional arc (e.g. tense under a "disaster" beat, hopeful
under a "things get better" beat), **sidechain-ducked** so speech stays fully
intelligible. Today the main pipeline has **no music** — narration is the only
audio; only outros (built/appended separately) carry music.

Music is a new, optional **audio axis** orthogonal to the visual axis: a per-scene
mood tag drives a global mix step. Off by default — existing storyboards render
exactly as before until a scene opts in.

**Constraint:** free / license-clear tracks only (YouTube Audio Library), $50/mo
budget. No on-screen or description credit required (see Track Library → license).

## First test target

Project `20260504-115232-baby-walker-story`, the **s19→s23 dark→hopeful arc**:

- **tense** under s19–s20 (injury mechanisms still extending; the undercount —
  "it's worse than the numbers say"),
- **crossfade to hopeful** at the s20→s22 boundary (≈ 234.5 s) into s22
  (a researcher sounds the alarm) and s23 (the decline curve — regulation worked),
- silence resumes at s24.

(s21 was cut in the 2026-05-29 quality pass; `scenes.json` confirms s20 → s22.)

**Acceptance:** zh-TW narration stays fully intelligible under the bed; music is
audible as texture during speech and recovers in inter-scene pauses; no music
before s19 or after s23.

---

## Why per-scene mood (not a section map)

`Scene` already carries a `section` (hook/context/rising/climax/aftermath/analysis),
so a section→mood map was considered. It is **insufficient**: in the baby-walker
target the `climax` section alone spans three moods — hopeful (s22–s23, regulation
worked) → critical (s25–s26, US inaction + lobbying) → cautionary (s27–s29, "it
doesn't even help"). One mood per section cannot express a mid-section pivot. Mood
is therefore an **independent per-scene axis** with inheritance, not a function of
`section`.

---

## Schema (the audio axis)

Two optional fields in `src/pipeline/storyboard.py`. Both default to "off", so
existing storyboards deserialize unchanged.

### `Scene.music_mood: str = ""`

Enum: `tense | somber | hopeful | triumphant | reflective | none`, plus `""`.

- `""` (default) → **inherit** the previous scene's effective mood (tag only the
  scenes where the mood *changes*).
- `none` → **explicit silence**; also propagates forward like any other mood.
- A named mood → start/continue that mood's bed.

### `Theme.music_default_mood: str = "none"`

Base mood at video start and for any scene that inherits before the first explicit
tag. Default `none` ⇒ the video is silent until a scene opts in.

### Effective-mood resolution

Walk scenes in storyboard order:

```
eff[0]   = scenes[0].music_mood or theme.music_default_mood
eff[i]   = scenes[i].music_mood or eff[i-1]
```

A **cue** is a maximal contiguous run of one effective mood. Cue *spans* (start/end
seconds) come from `compose/scenes.json` (`start_sec` + `duration_sec`), which is
already scaled to the true rendered video duration. `none` cues are silence gaps.

**Baby-walker resolved tags:** theme `none`; `s19=tense`, `s22=hopeful`, `s24=none`.
Resolution → s1–s18 `none`, s19 `tense`, s20 `tense` (inherit), s22 `hopeful`,
s23 `hopeful` (inherit), s24+ `none`. Cues: `tense [s19.start, s20.end)`,
`hopeful [s22.start, s23.end)`.

---

## Track library

Mirrors the existing `assets/sfx/` convention (license-clear asset dir + `.gitkeep`).

- **Layout:** `assets/music/<mood>/<track>.mp3` — one bed per named mood
  (`tense`, `somber`, `hopeful`, `triumphant`, `reflective`). `none` has no track.
  Five beds sourced up front (per the chosen "small palette"); the first render uses
  only `tense` + `hopeful`, the rest are ready for the Phase-2 extension.
- **Source + license:** YouTube Audio Library, filtered to **"Attribution not
  required."** This keeps the main video credit-free, consistent with the project
  rule "never add source credits unless explicitly asked." (Provenance is still
  recorded — see manifest — for hygiene, mirroring the SFX spec's CC0 record.)
- **Format specs:** 48 kHz stereo MP3 (matches the narration bus), normalized to
  **≈ −20 LUFS** pre-duck so the sidechain has consistent headroom across moods.
  Each bed ≥ 60 s (looped if a cue is longer).
- **Manifest** `assets/music/library.json` — the selection record + credit-tracking:

  ```json
  {
    "tense":      {"file": "tense/<name>.mp3",      "title": "", "artist": "",
                   "source": "YouTube Audio Library", "source_url": "",
                   "license": "Attribution not required",
                   "duration_s": 0, "loudness_lufs": -20.0},
    "somber":     { "...": "..." },
    "hopeful":    { "...": "..." },
    "triumphant": { "...": "..." },
    "reflective": { "...": "..." }
  }
  ```

- **Per-mood selection criteria** (binding contract for acquisition — what makes a
  bed "right" for the mood, so the choice isn't arbitrary):

  | Mood       | Character |
  |------------|-----------|
  | tense      | sparse minor drone / low pulse, no melody, slow build, ~60–80 felt bpm |
  | somber     | slow minor pad / lone piano, reflective-sad, minimal percussion |
  | hopeful    | warm major pads + gentle piano/strings, gradually rising, ~80–100 bpm |
  | triumphant | major, fuller arrangement, forward momentum / light percussion, resolved |
  | reflective | neutral-warm ambient, steady, low emotional charge (analysis beats) |

Beds are downloaded during implementation (as `assets/sfx/page_turn.wav` was created
out-of-band) and their real `title/artist/source_url/duration/loudness` written into
the manifest. The manifest — not this prose — is the source of truth for which file
backs each mood.

---

## Mix — global, sidechain-ducked (not per-clip)

Because each scene clip already embeds its own narration segment and the compose
concat normalizes + joins them, the music is mixed **once over the final concatenated
audio**, never into individual clips.

### Step 1 — build the mood bed (regenerable artifact)

Produce `compose/music/bed_<locale>.m4a`, a full-length bed aligned to the video
timeline:

- For each non-`none` cue `[start, end)` with mood `m`: take `library[m].file`,
  loop (`aloop`) or trim to the cue length (**plus a ~1.2 s tail** where the next cue
  is also non-`none`, so adjacent cues can overlap).
- **Crossfade by overlap, not dip-to-silence.** Where two non-`none` cues are adjacent
  at boundary `t`, place the *incoming* segment to begin ~1.2 s early (`adelay` to
  `t − 1.2 s`) so it overlaps the outgoing cue's tail; give the outgoing an
  equal-power `afade` out over `[t − 1.2, t]` and the incoming an equal-power `afade`
  in over the same window. `amix` then sums the overlap into a true crossfade. Where a
  cue borders a `none` gap (or the video edge), it simply fades to/from silence over
  ~1.2 s — no overlap.
- `amix` all placed segments (`normalize=0`) into one full-length stereo bed.

The bed contains **no ducking yet** — it is the inspectable, deterministic artifact;
re-running with the same moods + `scenes.json` + library reproduces it byte-for-byte.

### Step 2 — sidechain-duck + amix, per final variant

The speech key/bus is **`compose/raw.mp4`'s audio** — the pristine pre-music narration
master. Crucially this is *never* the file Step 2 overwrites, so every run starts from
clean narration (this is what makes re-runs idempotent — see below). `raw.mp4` and
`raw_no_overlay.mp4` share the same audio, so `raw.mp4` is the canonical source for both
variants. For each present `final_<locale>_*.mp4`, take its (subtitled) **video**, mix
clean narration + ducked bed, and remux:

```
ffmpeg -y \
  -i final_<locale>_<variant>.mp4   \  # 0: subtitled video (its audio is ignored)
  -i compose/raw.mp4                \  # 1: pristine narration — key + bus
  -i compose/music/bed_<locale>.m4a \  # 2: mood bed
  -filter_complex "
    [1:a]asplit=2[sk][sm];
    [2:a]volume=-3dB[mv];
    [mv][sk]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[duck];
    [sm][duck]amix=inputs=2:normalize=0:duration=first[mix]
  " \
  -map 0:v -c:v copy -map "[mix]" -c:a aac -b:a 192k <atomic tmp>   # → final
```

- Audio is sourced from `raw.mp4` (input 1), **never** from the final being overwritten
  (input 0 contributes only its video stream). This is what makes re-runs idempotent;
  it also gives both variants identical audio from one bed.
- `asplit` duplicates clean narration: one copy keys the compressor, one is the bus
  mixed back in.
- `sidechaincompress` pushes the bed ~−15 dB under narration during speech, recovering
  toward its resting level in inter-scene pauses. `attack 5 ms / release 300 ms` keeps
  zh-TW syllables from being masked while avoiding audible pumping. `--duck-db` tunes
  the target depth.
- `-c:v copy` ⇒ no video re-encode / no scene re-render; burned subtitles untouched.
- Written atomically (`run_ffmpeg_atomic`) over the existing final.
- **Short-circuit:** if the cue plan is empty (all `none`), Step 2 does nothing — the
  finals are left byte-for-byte unchanged (no lossy re-encode) and no bed is emitted.

Duck depth is exposed as `--duck-db` (default the values above) for quick tuning.

### Outro safety (by construction)

The outro is concatenated **at publish** (`publish/stage.py` →
`final_with_outro.mp4`), downstream of the compose final this step writes to, and the
bed spans only scene cues from `scenes.json`. So music can never bleed into the
outro, and the outro keeps its own music. Ordering: `compose` → `compose music` →
`publish`.

---

## CLI — `pipeline compose music`

New subcommand in `src/pipeline/cli_compose.py`, a sibling of `reburn`:

```bash
uv run pipeline compose music --project-id <ID> [--dry-run] [--duck-db -15]
```

- Loads `context.json`, the storyboard, and `compose/scenes.json`.
- Resolves effective moods → cue plan; builds the bed (Step 1); ducks + remuxes onto
  every present `final_<locale>_*.mp4` (Step 2). The preferred-variant final
  (`ctx.final_video_path`, which publish consumes) thereby gains music.
- If the cue plan is empty (all `none`), **short-circuits**: leaves the finals untouched
  and emits no bed (the feature-off no-op — no lossy re-encode).
- `--dry-run`: print the resolved cue plan (each cue's mood, `[start, end)`, chosen
  bed file, loop count) and exit — no render. The fast way to sanity-check tags.
- Logs a `SessionEntry` (`command="compose music"`) like `reburn`.
- **Errors loudly** if a tagged mood has no bed in the manifest/library (never
  silently drops a cue).

### Idempotency / ordering with reburn

**Idempotent by construction.** Step 2 always sources narration from the pristine
`raw.mp4`, never from the final it overwrites — so running `compose music` any number of
times yields the same result as running it once (music never doubles). Re-running is
expected: both the `--duck-db` tune loop and re-running after a reburn rely on this.

`compose music` is the **last audio-finishing pass**. A `compose reburn` rebuilds a
final's *video* from `raw` and stream-copies `raw`'s (clean) audio, so it removes the
music — re-run `compose music` afterward:

> Re-run `compose music` after any `reburn`.

The persisted `bed_<locale>.m4a` makes re-runs cheap (Step 1 is skipped when the bed is
up to date w.r.t. moods + `scenes.json`). *Future enhancement:* make `reburn`
music-aware — re-apply the persisted bed automatically after burning subtitles.

---

## Changes (file-by-file)

### New: `src/pipeline/composer/music.py`
- `MUSIC_MOODS = ("tense","somber","hopeful","triumphant","reflective","none")`.
- `load_library() -> dict[str, MoodTrack]` (reads `assets/music/library.json`).
- `resolve_effective_moods(storyboard) -> list[tuple[str, str]]` (scene_id, mood).
- `plan_cues(storyboard, scenes_json) -> list[Cue]` (mood, start_sec, end_sec).
- `build_bed(cues, library, out_path)` — Step 1 (loop/trim/adelay/afade/amix).
- `duck_and_mux(final_video, raw_audio, bed_path, duck_db)` — Step 2 (3-input mux:
  final's video + pristine `raw.mp4` audio + bed → sidechaincompress + amix).
- Pure planning functions (`resolve_*`, `plan_cues`) unit-testable without ffmpeg.

### Edit: `src/pipeline/storyboard.py`
- `Scene.music_mood: str = ""`.
- `Theme.music_default_mood: str = "none"`.
- (No change to serialization beyond the new optional fields.)

### Edit: `src/pipeline/cli_compose.py`
- Add `@compose_app.command("music")` per the CLI section.

### New assets
- `assets/music/{tense,somber,hopeful,triumphant,reflective}/.gitkeep`
- `assets/music/library.json` (manifest; beds added during implementation).

### Docs
- README.md "Compose iteration" block + CLAUDE.md compose snippet: add
  `compose music` and the "re-run after reburn" note.

---

## Testing (mirrors the SFX spec's rigor)

**Unit — mood resolution** (`resolve_effective_moods`):
- inherit-on-blank; `none` propagation; theme-default head.
- Baby-walker table: s1–s18 `none`, s19 `tense`, s20 `tense`(inherit), s22 `hopeful`,
  s23 `hopeful`(inherit), s24+ `none`.

**Unit — cue planning** (`plan_cues`) on baby-walker `scenes.json`:
- two cues: `tense ≈ [s19.start, s20.end)`, `hopeful ≈ [s22.start, s23.end)`;
- the tense→hopeful boundary ≈ 234.5 s; no cue before s19 or after s23.

**Unit — errors:** a tagged mood absent from the library raises a clear error.

**Bed build:** `build_bed` produces an m4a of the expected total duration with
silence in `none` regions and audio in cue regions; deterministic across runs.

**Integration — baby-walker** (`compose music` end-to-end):
- the mood bed has non-silent energy within `[s19.start, s23.end]` and silence outside;
- **intelligibility — measured on the clean artifacts, not the mix.** Because narration
  (`raw.mp4`) and the mood bed are separate signals, derive the *ducked* bed (run Step 2's
  `sidechaincompress` on the bed keyed by `raw`'s audio — a deterministic intermediate)
  and compare it to narration directly: in speech windows (from the SRT) the ducked-bed
  RMS sits **12–15 dB below** `raw` narration RMS; in an inter-scene pause inside a cue
  the ducked-bed RMS rises toward its resting level (duck recovery). This is exact —
  no attempt to un-mix the final;
- `-c:v copy` honored (final's video stream bit-identical to pre-music; subtitles intact);
- no music before s19 or after s23.

**Regression — feature off:** a storyboard with no `music_mood` + theme `none` ⇒ the cue
plan is empty ⇒ `compose music` **short-circuits**: it touches no final files
(byte-for-byte unchanged — assert mtime/hash unchanged, no aac re-encode) and emits no
bed.

**Idempotency:** running `compose music` twice in a row produces a final whose audio
matches a single application (no music doubling) — guaranteed because Step 2 sources
narration from the unchanged `raw.mp4`, not the overwritten final.

---

## Scope / YAGNI

**In:** per-scene mood + theme default; 5-mood library; global sidechain-ducked mix;
`compose music` subcommand; baby-walker s19→s23 as the first render.

**Out (deferred):** rotating multi-track pools per mood (one bed per mood for now);
auto-suggesting moods from narration sentiment; per-scene volume automation; making
`reburn` music-aware; a dashboard music editor. The schema (one mood tag per scene)
does not grow a track-editing DSL.

**Phase 2 (quality-gated — Tim's call after judging v1):** extend moods across the
broader rising + climax sections (injury escalation: `tense`/`somber`; regulation
story: `hopeful`/`triumphant`/`reflective`) using the already-built 5-mood library.
**No new code — only more `music_mood` tags.**

## Governance

This is a visual-arsenal / pipeline-infrastructure capability. Per CLAUDE.md it
should be folded into `docs/ROADMAP.md` via the engineering-manager (**INTAKE**), and
a greenlit implementation sprint is not "done" until the EM passes it in **REVIEW**
against the regression test-plan before merge. This spec is the design input to that
flow; EM dispatch is left to Tim.
