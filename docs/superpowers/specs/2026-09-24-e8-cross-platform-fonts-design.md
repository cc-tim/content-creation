# Sprint 8 — E8 item 1: cross-platform font resolution + Linux-assumption audit

**Epic:** E8 (two-machine workflow & render portability) · **Status:** 🔵 proposed, Tim-greenlit
2026-09-24 as the next sprint · **Owner of acceptance:** engineering-manager (REVIEW gate)
**Build host:** Linux hub (this session). **The Mac (M3) is not reachable during the build.**
Acceptance is therefore split: **(A) hub-verifiable, must PASS before merge** and **(B)
Mac-verification, run by Tim on the Mac right after merge**. See the acceptance section.

---

## 1. Goal

One font resolver used by every renderer, loud when the right font is missing, so a render on
the Mac draws the same zh-TW (Traditional Chinese) glyphs as a render on the hub. Plus the other
Linux- and machine-specific assumptions that would break or quietly degrade a Mac render.

## 2. Axis (two-axes guard)

**Neither quality nor runtime.** This is a portability / iteration-speed item (E8). It adds zero
seconds and no new rendered capability. One side effect is a correctness fix (section 3.2: zh-TW
PIL text has been drawn with Hong Kong glyph forms). Record that as a bug fix. Do not cite it as
a quality-axis gain for this sprint.

## 3. Problem (grounded 2026-09-24 on the hub)

### 3.1 Hardcoded Linux paths and silent fallbacks
| Site | Today | Mac failure |
|---|---|---|
| `composer/rich_slide.py:22-25` `_SANS_*`/`_SERIF_*` + `_load_font` | `/usr/share/fonts/opentype/noto/*.ttc` | `OSError`: chart, chart_anim and callout all import these constants (`chart_anim.py:125,272,341`, `callout.py:142`) |
| `outro/builder.py:13-14` | drawtext `fontfile=/usr/share/.../NotoSansCJK-*.ttc` | ffmpeg error: file not found |
| `compartment_renderers/running_out.py:16-31` | Linux path list + PingFang, then **`load_default()`** | Silent PingFang substitution (different design) or tofu (empty boxes) |
| `stages/compose.py:247-253` `_title_font` | bare `NotoSerifCJK-Regular.ttc` → DejaVu → **`load_default()`** | Silent tofu / bitmap font, no error |
| drawtext `font='Noto Sans CJK TC'` (`overlay.py`, `slide.py`, `text_card.py`, `compose.py:55`, `storyboard.py:262`) and libass `FontName=` (`utils/ffmpeg.py:47`) | Family name resolved by fontconfig/libass | fontconfig **silently substitutes** a missing family. Checked on the hub: `fc-match 'Nonexistent Font XYZ'` returns Noto Sans with exit 0 |

### 3.2 Latent bugs found during grounding (these are in scope because the resolver fixes them)
- **`_TC_INDEX = 4` is the HK face, not TC.** On the hub, `NotoSansCJK-Bold.ttc` has face 3 =
  `Noto Sans CJK TC` and face 4 = `Noto Sans CJK HK`. It is the same for Serif. Every zh-TW PIL
  render to date (charts, animated charts, callouts, rich_slide) drew **HK glyph forms**.
  Measured: Latin text renders byte-identical between face 3 and face 4, so no existing golden
  changes. CJK text differs (for example 說/為/溫/裡/着).
- **The outro uses face 0 = JP.** drawtext `fontfile=` on a TTC loads face 0 and has no
  face-index option, so the zh-TW outro ("訂閱頻道") renders with Japanese glyph forms.
- **`_title_font` loads face 0 (JP) of the serif TTC** by bare filename.

### 3.3 Other machine assumptions (audit results)
| Site | Assumption | Disposition |
|---|---|---|
| `cli_storyboard.py:428` `Path("output/projects")` | cwd-relative literal | → `PipelineConfig().OUTPUT_DIR / "projects"` (IN) |
| `utils/gallery.py:23` `GALLERY_DIR = Path("output/gallery")` (import-time constant) | literal | → derived from `OUTPUT_DIR` at call time (IN) |
| `composer/base.py:365,391` `Path("output/gallery/gallery_index.json")` | literal | → shared gallery-path helper (IN) |
| `tests/unit/test_memory_sync.py` imports `~/.claude/bin/memory_sync` | home-dir tool present | **Already fails collection on the hub today.** It will also break `docs/mac-setup.md` step 7 (`uv run pytest -q`). → `pytest.importorskip` with a reason (IN) |
| `providers/gen_image.py:14`, `providers/edit_image.py:14` need `~/.claude/bin/*.py` | home-dir tools present | `docs/mac-setup.md` copies only `api-keys.json`. On the Mac, `gen-image` raises `ProviderError` and rich_slide **falls back to a flat background** (logged, but it quietly lowers quality). → `pipeline doctor` FAILS on it + add a mac-setup line (IN). Making rich_slide's fallback itself loud is OUT (E5 follow-on, already listed) |
| `dashboard/server.py:1288` `systemctl --user` | Linux | Hub-only by design (the dashboard runs on the hub). Document it, no change |
| `session_log.py:32` `~/.claude/projects/<cwd-slug>` | slug from cwd | Portable (uses cwd). No change |
| `animation_review.py` | earlier note suspected a playwright/chromium path | **Not present**: it uses only ffmpeg/ffprobe. Close the audit item |
| ~30 other `subprocess.run` sites | ffmpeg/ffprobe/python3 on PATH | Portable if the tools are installed. ffmpeg *capabilities* (drawtext / fontconfig / libass) are checked by `pipeline doctor` |

## 4. Approach

### 4.1 `src/pipeline/utils/fonts.py` (new): the one resolver
```python
class FontResolutionError(RuntimeError):   # carries .suggested_fix (platform-specific)
    ...

@dataclass(frozen=True)
class ResolvedFont:
    path: Path
    index: int            # TTC face index, found by NAME, never hardcoded
    family: str           # e.g. "Noto Sans CJK TC"
    style: str            # "Regular" | "Bold"

Role = Literal["sans", "serif"]
Weight = Literal["regular", "bold"]

def resolve_font(role: Role, weight: Weight, region: str = "TC") -> ResolvedFont   # lru_cached
def load_pil_font(role: Role, weight: Weight, size: int, region: str = "TC") -> ImageFont.FreeTypeFont
def drawtext_font_arg(weight: Weight = "regular", family: str = "Noto Sans CJK TC") -> str
    # returns the escaped `font=...` drawtext option (a fontconfig pattern incl. style), never fontfile=
def verify_fontconfig_family(family: str, style: str | None = None) -> str
    # runs `fc-match -f '%{family}|%{style}'`; raises FontResolutionError if the returned
    # family list (comma-separated) does not contain `family` → no silent substitution.
```
**Resolution order** (first hit wins; every candidate is **verified by opening it and checking
`font.getname() == (family, style)`**, and TTC faces are scanned by name):
1. **Explicit override:** `PIPELINE_FONT_DIRS` (split on `os.pathsep`). Dirs are scanned for
   Noto CJK files.
2. **fontconfig:** `fc-match -f '%{file}|%{index}' 'Noto Sans CJK TC:style=Bold'`, then the
   name check. Skipped if `fc-match` is absent.
3. **Known platform dirs:** Linux `/usr/share/fonts/{opentype,truetype}/noto`,
   `~/.local/share/fonts`. macOS `~/Library/Fonts`, `/Library/Fonts`,
   `/opt/homebrew/share/fonts`. Accept any packaging: Debian per-weight `.ttc`, the Homebrew
   cask Super-OTC `NotoSansCJK.ttc`, or per-region `.otf`. Face selection is by name.
4. **Raise `FontResolutionError`** with `suggested_fix`: Linux `sudo apt install fonts-noto-cjk`;
   macOS `brew install --cask font-noto-sans-cjk font-noto-serif-cjk && fc-cache -f`.

**No cross-family substitution, ever.** PingFang, DejaVu and `load_default()` are removed. A
Mac final must look like a hub final. A different CJK family would pass a "has glyphs" check
while breaking cross-machine consistency, so it counts as a failure.

### 4.2 Call-site migration
- `rich_slide.py`: delete the path constants and `_TC_INDEX`. `_load_font` delegates to
  `load_pil_font`. Update the imports in `chart_anim.py` and `callout.py` (they import
  `_SANS_BOLD`/`_SERIF_BOLD`/`_load_font`; change the signature to role/weight, not path).
- `running_out.py`, `compose.py:_title_font`: use `load_pil_font`. Resolution failure
  **propagates** (loud). No fallback remains.
- `outro/builder.py`: `fontfile=` → `drawtext_font_arg("bold"/"regular")`. This also fixes the
  JP-face bug. Watch the escaping: `:` inside a fontconfig pattern must be escaped inside the
  filtergraph.
- drawtext `font='…'` sites (`overlay.py`, `slide.py`, `text_card.py`) and the libass
  `FontName`: keep the family name. `ComposeStage` runs `verify_fontconfig_family(theme font)`
  **once at compose start**, so a missing or substituted family fails before any scene
  renders, not after 40 minutes of rendering.
- Output paths: section 3.3 rows marked IN.

### 4.3 `pipeline doctor` (new, minimal): the Mac-verification instrument
A render-readiness check that turns "does the Mac render CJK?" into one command with an exit
code and saved artifacts. **Scope-capped to font/ffmpeg/render readiness. It is not a general
health framework.**
- `pipeline doctor [--out DIR]`. Prints one PASS/FAIL line per check. Exit **0** all pass,
  **1** any FAIL.
- Checks:
  1. `resolve_font` for sans/serif × regular/bold → prints `path|index|family|style`. All
     four must be `Noto {Sans,Serif} CJK TC`.
  2. `verify_fontconfig_family` for the theme default family, Regular and Bold.
  3. `ffmpeg -buildconf` contains `--enable-libfreetype`, `--enable-libfontconfig`,
     `--enable-libass`, and `ffmpeg -filters` lists `drawtext` and `subtitles`.
  4. **Glyph-distinctness probes** (render-truth, no OCR, platform-agnostic). Render two
     different CJK strings (for example `說明` vs `學步`) plus one private-use codepoint
     (U+E000 → .notdef box) through (a) PIL `load_pil_font`, (b) drawtext via
     `drawtext_font_arg`, (c) libass subtitle burn. PASS iff the two CJK renders differ from
     each other **and** neither equals the .notdef render (tofu renders every char as the same
     box). Save the probe PNGs to `--out`.
  5. `~/.claude/bin/gen-image.py` + `keymanager.py` present. FAIL, because without them every
     rich_slide background quietly degrades to flat.
- The probe functions live in `utils/fonts.py` (or `utils/font_probe.py`) so the integration
  test and the CLI share one implementation.

### 4.4 Golden/snapshot policy for macOS: **decided here, not by the build**
**Hub (Linux) goldens are canonical. On macOS, golden-comparison asserts are SKIPPED with an
explicit, counted reason. Determinism tests run everywhere.**
- Rationale: goldens compare byte-exact (`ImageChops.difference(...).getbbox() is None`). The
  Mac will have a different Noto build (Homebrew Super-OTC vs Debian per-weight TTC) and
  possibly a different freetype/raqm, so byte-exact Latin glyphs cannot be assumed. A pixel
  tolerance is a rabbit hole: loose enough for rasterizer drift means loose enough to miss a
  real layout regression. Layout regressions are caught on the hub, which renders nightly
  anyway.
- Mechanics (build implements exactly this):
  - New shared helper `tests/golden_policy.py` with `assert_matches_golden(img, golden_path)`.
    It replaces the three duplicated `_assert_golden` helpers in `tests/unit/test_chart.py`,
    `test_chart_anim.py` and `test_callout.py`.
  - If `sys.platform != "linux"` and `PIPELINE_GOLDEN_STRICT` is unset, call
    `pytest.skip("golden PNGs are hub-canonical (linux); set PIPELINE_GOLDEN_STRICT=1 to compare")`.
  - `UPDATE_GOLDENS=1` on non-linux → **hard error** ("goldens regenerate on the hub only"). A
    Mac must never overwrite canonical goldens.
  - `PIPELINE_GOLDEN_STRICT=1` forces comparison on any platform. The Mac runs it once,
    **informational only**, to record whether goldens happen to match there. That is data for
    a later decision, not an acceptance criterion.
  - **Determinism tests (render twice → identical) are NOT skipped anywhere.** They are
    platform-agnostic and still catch nondeterminism on the Mac.
- Expected hub impact: **zero golden regenerations.** All current goldens are Latin-only and
  face 3 == face 4 for Latin (measured). If any golden drifts on the hub, that is a finding.
  Stop and report it; do not `UPDATE_GOLDENS` it away.

### 4.5 Fences in code (standing lesson: guardrails belong in code, not docs)
A static-audit unit test fails if `src/pipeline/**/*.py` contains: `/usr/share/fonts`,
`/System/Library/Fonts`, `ImageFont.load_default(`, `ImageFont.truetype(` outside
`utils/fonts.py`, `fontfile=` in a drawtext string, or `Path("output/` / `"output/gallery"`
outside `config.py`. Without this, the audit will not stay done.

## 5. Scope

**IN**
- `src/pipeline/utils/fonts.py` (resolver, `FontResolutionError`, `drawtext_font_arg`,
  `verify_fontconfig_family`, glyph probes).
- Migrate `rich_slide.py`, `chart_anim.py`, `callout.py`, `running_out.py`, `compose.py`
  (`_title_font` + compose-start fontconfig verification), `outro/builder.py`.
- Output-path fixes: `cli_storyboard.py:428`, `utils/gallery.py:23`, `composer/base.py:365,391`.
- `pipeline doctor` CLI (`src/pipeline/cli_doctor.py`, registered in `cli.py`).
- Golden policy helper + migrate the three golden test files.
- `tests/unit/test_memory_sync.py` → `pytest.importorskip("memory_sync", reason=...)`.
- `docs/mac-setup.md`: add `fc-cache -f` after the font casks, a `~/.claude/bin` copy step, a
  `pipeline doctor` step, and replace "Blocked until E8 item 1 merges" with a pointer to the Mac
  verification in this spec (section 8B).
- README: one line for `pipeline doctor` in the command reference.

**OUT (deferred)**
- Locale → region plumbing (ja → JP, es → Latin fonts). The resolver takes `region`, but
  callers pass the TC default. Rolls to the first non-zh-TW locale project.
- Making rich_slide's flat-background provider fallback loud → E5 follow-on (already listed).
- Checkout/checkin + hub lock → **E8 item 2**. Draft encoder profile / videotoolbox / nvenc →
  **E8 item 3**.
- Pixel-tolerance golden comparison, per-platform golden sets, CI → not needed. Revisit only if
  the informational `PIPELINE_GOLDEN_STRICT` Mac run shows goldens nearly match.
- Re-rendering existing projects to pick up TC forms. Not required. See risk R3.

## 6. Dependencies / unblocks
- **Depends on:** none.
- **Unblocks:** every Mac render (previews and finals). E8 item 2 becomes useful for the render
  half. The zh-TW HK/JP glyph-form bugs get fixed as a byproduct.
- **Does NOT:** add runtime (zero beats), add rendered capability, or speed up any render (that
  is E8 item 3).

## 7. Cost / size
- **$0.** No provider calls. Probes are local Pillow/ffmpeg renders. The real-scene checks
  reuse prompt-hash-cached backgrounds already in the project dir.
- **~1.5 build sessions** (the resolver and call sites are small. The doctor probes, golden
  helper and static fence account for the other half).

## 8. Acceptance criteria

### (A) Hub-verifiable. ALL must pass before merge (the EM runs these in REVIEW)
1. `uv run pytest tests/unit/test_fonts.py tests/unit/test_font_callsites.py tests/unit/test_golden_policy.py tests/unit/test_cli_doctor.py tests/unit/test_output_paths.py -q` → all pass.
2. `uv run pytest tests/integration/test_cjk_render_truth.py --integration -q` → all pass (PIL +
   drawtext + libass glyph-distinctness, real ffmpeg on the hub).
3. **Resolver identity on the hub:** `resolve_font("sans","bold")` → `NotoSansCJK-Bold.ttc`
   **index 3**, family `Noto Sans CJK TC`. Same for all four role/weight combos, asserted in
   `test_fonts.py`. This locks in the HK→TC fix.
4. **Loud failure:** with the resolver forced to find nothing, `_title_font`, `running_out`
   and `rich_slide` raise `FontResolutionError` whose `suggested_fix` names the platform
   install command. `verify_fontconfig_family("Nonexistent Font XYZ")` raises. There is no
   `load_default` anywhere (static fence).
5. **Existing goldens unchanged:** `uv run pytest tests/unit/test_chart.py tests/unit/test_chart_anim.py tests/unit/test_callout.py -q` passes **without** `UPDATE_GOLDENS`, and
   `git diff --stat tests/fixtures/` is empty.
6. Golden policy unit-tested: with `sys.platform` monkeypatched to `darwin`, compare → skip
   with the documented reason, `UPDATE_GOLDENS=1` → raises, `PIPELINE_GOLDEN_STRICT=1` →
   compares.
7. `uv run pipeline doctor --out tmp/e8-fonts/hub` → exit 0, all checks PASS, probe PNGs saved.
8. **Hub real-scene check** (behavior changed on the hub, so this is required even though it is
   an infra sprint). Render baby-walker `s11` (chart stat_big_number, CJK title), `s31`
   (text_card) and `s24` (article_image + overlay) on master and on the branch. Save the
   side-by-side to `tmp/e8-fonts/hub/before_after_{s11,s31,s24}.png`. Expected: s11 CJK
   glyphs show HK→TC form changes only (layout and Latin identical); s31/s24 unchanged
   (drawtext was already using fontconfig TC). The outro: render once and save
   `tmp/e8-fonts/hub/outro_after.png` showing TC forms for 訂閱頻道.
9. Full suite: `uv run pytest -q` → **zero collection errors** (the `test_memory_sync`
   importorskip) and zero failures. Baseline before the sprint: 1143 passed / 10 skipped with
   that file ignored.
10. `uv run ruff check src/ tests/` and `uv run mypy src/` clean.
11. A separate code-correctness review happened (not the builder, not the EM). Its findings are
    resolved or explicitly deferred.

### (B) Mac verification. Tim runs these on the M3 right after merge
The EM cannot run the Mac. The sprint is merged on (A) PASS and **stays 🔵 until (B) evidence is
supplied**. It flips to 🟢 at a short EM follow-up REVIEW of the (B) artifacts. This is the same
pattern as the E7 music "ADVISE until demo" precedent: merge on engineering, advance on proof.

```bash
# 0. Prereqs (once). Fonts + fontconfig cache + home-dir tools
brew install --cask font-noto-sans-cjk font-noto-serif-cjk && fc-cache -f
mkdir -p ~/.claude/bin && scp 'hub:.claude/bin/{gen-image.py,keymanager.py}' ~/.claude/bin/
cd ~/content-creation && git pull && uv sync

# 1. ffmpeg capability. Expect all four enable flags printed and drawtext + subtitles listed
ffmpeg -hide_banner -buildconf | grep -E 'enable-(libfreetype|libfontconfig|libass|libharfbuzz)'
ffmpeg -hide_banner -filters | grep -E ' (drawtext|subtitles) '
#    If any is missing: `brew install ffmpeg-full` and put it first on PATH (it may be keg-only),
#    then re-run step 1. Record which ffmpeg you ended up with.

# 2. Render-readiness doctor. Expect exit 0, every line PASS
uv run pipeline doctor --out tmp/e8-fonts/mac ; echo "exit=$?"
#    Expect check 1 to print family "Noto Sans CJK TC"/"Noto Serif CJK TC" for all four faces
#    (path under ~/Library/Fonts, index = whatever the Super-OTC uses; the index will NOT be 3)

# 3. Test suite. Expect 0 failures; golden-compare tests SKIPPED with the hub-canonical reason
uv run pytest -q -rs 2>&1 | tail -25
uv run pytest tests/integration/test_cjk_render_truth.py --integration -q
#    Informational only (not acceptance): does the Mac match hub goldens byte-exact?
PIPELINE_GOLDEN_STRICT=1 uv run pytest tests/unit/test_chart.py tests/unit/test_chart_anim.py tests/unit/test_callout.py -q 2>&1 | tail -3

# 4. Real-scene render truth (probe copy; do NOT check this copy back in to the hub)
ID=20260504-115232-baby-walker-story
HUBP=/mnt/windows_ssd/content-creation/output/projects
rsync -rlt --modify-window=2 hub:$HUBP/$ID/ ~/content-creation/output/projects/$ID/
uv run pipeline compose set-variant --project-id $ID --variant subtitles   # overlays + burned subs
uv run pipeline compose rescene --project-id $ID --scene s11 --scene s31 --scene s24
uv run pipeline visual-review extract-frames --project-id $ID
#    Copy the extracted frames for s11, s31, s24 to tmp/e8-fonts/mac/ and serve them:
#    s11 = chart with CJK title, s31 = text_card, s24 = image + overlay text + burned subtitle
```
**Expected evidence (B), sent back to the EM:**
- B1. Step 1 output: the four `--enable-*` flags present, drawtext and subtitles listed.
- B2. `pipeline doctor` exit 0. Its stdout, plus `tmp/e8-fonts/mac/*.png` probes where the two
  CJK probes visibly differ and neither is a box.
- B3. `pytest -q -rs` tail: 0 failed, 0 errors. The skipped list shows only golden-compare
  skips with the hub-canonical reason plus pre-existing skips. **Any other Mac-only failure
  gets triaged:** a font/path/platform assumption → this sprint (REWORK). Anything unrelated →
  logged as an E8 follow-up. Never silently ignored.
- B4. `test_cjk_render_truth.py --integration` passes on the Mac.
- B5. Frames for **s11, s31, s24** in which the CJK characters are real Traditional-Chinese
  glyphs (no boxes, no blanks), in the Noto look (not PingFang), with layout matching the hub
  `after` renders from A8. Tim eyeballs them side by side with `tmp/e8-fonts/hub/`.
- B6. (Informational) the `PIPELINE_GOLDEN_STRICT=1` result: pass or number of drifted
  goldens. The EM records it. It does not gate.

## 9. Risks
- **R1. Escaping of the fontconfig pattern in drawtext** (`Noto Sans CJK TC\:style=Bold` inside
  a filter option). Mitigation: `drawtext_font_arg` is the only builder, and the drawtext
  probe exercises that exact string.
- **R2. The Homebrew ffmpeg build may lack fontconfig/libass** (Homebrew has slimmed the
  default formula before). Mitigation: Mac step 1 plus doctor check 3. The fallback is
  `ffmpeg-full`. Do not guess; the doctor tells.
- **R3. Mixed-font projects.** A partial `rescene` of an older project renders the new scenes
  with TC forms and leaves the old scenes in HK forms. The difference is nearly invisible (a
  handful of characters) but it exists. Mitigation: note it in the PR. A full rebuild before
  republishing an old project removes it. Not a blocker.
- **R4. libass on macOS may use CoreText, not fontconfig**, so `verify_fontconfig_family` does
  not prove the subtitle font choice there. Mitigation: doctor probe 4(c) plus the B5 eyeball of
  the s24 burned subtitle. Residual risk: CoreText picks a different family that still has CJK
  glyphs. B5 catches that visually.
- **R5. `fc-match` absent on the Mac** (fontconfig CLI not installed). The resolver skips step 2
  and uses the known dirs. `verify_fontconfig_family` raises with `brew install fontconfig`.
  That is correct, because drawtext `font=` needs fontconfig anyway.

## 10. Test-plan rows (appended to `.agent-memory/engineering-manager/test-plan.md`, 🔲 planned)
See the E8 section of the test plan. The REVIEW checklist is exactly those rows.
