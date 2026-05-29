# Music Audio-Axis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement task-by-task. Steps use `- [ ]` checkboxes. Executor (Claude) has full repo context — keep ceremony low; the real detail is in the music.py API, the ffmpeg filtergraphs, and the test assertions.

**Goal:** Add an optional background-music layer on the audio axis — a per-scene mood tag drives a global, sidechain-ducked music bed mixed under the narration via a new `pipeline compose music` subcommand.

**Architecture:** Per-scene `Scene.music_mood` (+ `Theme.music_default_mood`) resolves (inherit-on-blank) to per-scene effective moods; combined with `compose/scenes.json` spans → cues. A full-length mood bed (48 kHz/stereo, mood crossfades) is sidechain-ducked under the **pristine `raw.mp4`** narration (never the overwritten final → idempotent), then amixed onto each `final_<locale>_*.mp4` (video stream-copied). Spec: `docs/superpowers/specs/2026-05-29-music-audio-axis-design.md`.

**Tech Stack:** Python 3.12, dataclasses, typer (CLI), ffmpeg (`aloop`/`adelay`/`afade`/`amix`/`sidechaincompress`), pytest.

**Working location:** worktree `/home/tim-huang/cc-music-audio-axis` on branch `feat/music-audio-axis`. Commit each task; **do NOT merge to master** (EM REVIEW is definition-of-done).

**Hazard (read before any run):** `mux_music_onto_final` atomically **overwrites** `final_*.mp4`. NEVER point `OUTPUT_DIR` at the live `/home/tim-huang/content-creation/output` (destroys baby-walker's in-flight finals). Any real-project run is on a **copy** in a scratch `OUTPUT_DIR`.

---

### Task 1: Schema — `Scene.music_mood` + `Theme.music_default_mood`

**Files:** Modify `src/pipeline/storyboard.py`; Test `tests/unit/test_storyboard_music_mood.py`

- [ ] **Test first** — round-trip + defaults:
```python
from pipeline.storyboard import Scene, Theme, Storyboard

def test_scene_music_mood_defaults_empty_and_roundtrips():
    sc = Scene(id="s1", section="rising", narration="x", narration_est_sec=1.0)
    assert sc.music_mood == ""
    sc.music_mood = "tense"
    assert Scene.from_dict(sc.to_dict()).music_mood == "tense"

def test_scene_music_mood_omitted_when_empty():
    sc = Scene(id="s1", section="rising", narration="x", narration_est_sec=1.0)
    assert "music_mood" not in sc.to_dict()          # stays clean for untagged scenes

def test_theme_music_default_mood_roundtrips():
    t = Theme(music_default_mood="hopeful")
    assert Theme.from_dict(t.to_dict()).music_default_mood == "hopeful"
    assert Theme().music_default_mood == "none"      # default
```
- [ ] **Implement:**
  - `Scene`: add field `music_mood: str = ""` (with the other defaulted fields, after `subtitle_override`).
  - `Scene.from_dict`: add `music_mood=data.get("music_mood", "")` to the `cls(...)` call.
  - `Scene.to_dict`: append `if self.music_mood: out["music_mood"] = self.music_mood`.
  - `Theme`: add field `music_default_mood: str = "none"`. Add `"music_default_mood": self.music_default_mood` to `Theme.to_dict` (`from_dict` already loads any dataclass field).
- [ ] Run `uv run pytest tests/unit/test_storyboard_music_mood.py -v` → PASS. Commit.

---

### Task 2: `music.py` — moods enum, library loader, mood resolution

**Files:** Create `src/pipeline/composer/music.py`; Test `tests/unit/test_music_resolve.py`

- [ ] **Test first:**
```python
from pipeline.composer.music import resolve_effective_moods, MUSIC_MOODS
from pipeline.storyboard import Scene, Theme, Storyboard

def _sb(theme_default, *mood_by_id):
    scenes = [Scene(id=i, section="rising", narration="x", narration_est_sec=1.0, music_mood=m)
              for i, m in mood_by_id]
    return Storyboard(theme=Theme(music_default_mood=theme_default), scenes=scenes)

def test_inherit_and_none_propagation():
    sb = _sb("none", ("s1",""),("s2","tense"),("s3",""),("s4","hopeful"),("s5",""),("s6","none"),("s7",""))
    assert dict(resolve_effective_moods(sb)) == {
        "s1":"none","s2":"tense","s3":"tense","s4":"hopeful","s5":"hopeful","s6":"none","s7":"none"}

def test_theme_default_heads_the_video():
    assert dict(resolve_effective_moods(_sb("reflective", ("s1",""),("s2","")))) == {"s1":"reflective","s2":"reflective"}

def test_invalid_mood_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_effective_moods(_sb("none", ("s1","banana")))
```
- [ ] **Implement** (`music.py`):
```python
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

MUSIC_MOODS = ("tense", "somber", "hopeful", "triumphant", "reflective", "none")
_REPO_ROOT = Path(__file__).resolve().parents[3]
MUSIC_LIBRARY_JSON = _REPO_ROOT / "assets" / "music" / "library.json"
_XFADE_SEC = 1.2
_EDGE_FADE_SEC = 0.8

@dataclass(frozen=True)
class MoodTrack:
    mood: str
    file: Path

def resolve_effective_moods(storyboard) -> list[tuple[str, str]]:
    eff = storyboard.theme.music_default_mood or "none"
    out: list[tuple[str, str]] = []
    for sc in storyboard.scenes:
        m = sc.music_mood or ""
        if m and m not in MUSIC_MOODS:
            raise ValueError(f"scene {sc.id}: unknown music_mood {m!r} (allowed: {MUSIC_MOODS})")
        if m:
            eff = m
        out.append((sc.id, eff))
    return out

def load_library(path: Path = MUSIC_LIBRARY_JSON) -> dict[str, MoodTrack]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lib: dict[str, MoodTrack] = {}
    for mood, entry in data.items():
        f = (Path(path).parent / entry["file"]) if entry.get("file") else None
        if f:
            lib[mood] = MoodTrack(mood=mood, file=f)
    return lib
```
- [ ] Run the test → PASS. Commit.

---

### Task 3: `music.py` — `plan_cues`

**Files:** Modify `src/pipeline/composer/music.py`; Test `tests/unit/test_music_cues.py`

- [ ] **Test first** (baby-walker-shaped fixture: tense s19–s20 → hopeful s22–s23, none elsewhere):
```python
from pipeline.composer.music import plan_cues, Cue
from pipeline.storyboard import Scene, Theme, Storyboard

def test_plan_cues_two_contiguous_cues_with_boundary():
    ids_sections = [("s19","rising","tense"),("s20","rising",""),("s22","climax","hopeful"),
                    ("s23","climax",""),("s24","climax","none")]
    sb = Storyboard(theme=Theme(music_default_mood="none"),
        scenes=[Scene(id=i,section=s,narration="x",narration_est_sec=1.0,music_mood=m) for i,s,m in ids_sections])
    scenes = [{"id":"s19","start_sec":211.5,"duration_sec":11.6},
              {"id":"s20","start_sec":223.1,"duration_sec":11.4},
              {"id":"s22","start_sec":234.5,"duration_sec":15.6},
              {"id":"s23","start_sec":250.1,"duration_sec":11.8},
              {"id":"s24","start_sec":261.9,"duration_sec":16.0}]
    cues = plan_cues(sb, scenes)
    assert [(c.mood, round(c.start_sec,1), round(c.end_sec,1)) for c in cues] == [
        ("tense",211.5,234.5), ("hopeful",234.5,261.9)]   # merged contiguous; boundary at 234.5

def test_plan_cues_empty_when_all_none():
    sb = Storyboard(theme=Theme(music_default_mood="none"),
        scenes=[Scene(id="s1",section="hook",narration="x",narration_est_sec=1.0)])
    assert plan_cues(sb, [{"id":"s1","start_sec":0.0,"duration_sec":5.0}]) == []
```
- [ ] **Implement:**
```python
@dataclass(frozen=True)
class Cue:
    mood: str
    start_sec: float
    end_sec: float
    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec

def plan_cues(storyboard, scenes: list[dict]) -> list[Cue]:
    moods = dict(resolve_effective_moods(storyboard))
    rows = sorted(scenes, key=lambda s: s["start_sec"])
    cues: list[Cue] = []
    for s in rows:
        mood = moods.get(s["id"], "none")
        if mood == "none":
            continue
        st = float(s["start_sec"]); en = st + float(s["duration_sec"])
        if cues and cues[-1].mood == mood and abs(cues[-1].end_sec - st) < 1e-2:
            cues[-1] = Cue(mood, cues[-1].start_sec, en)
        else:
            cues.append(Cue(mood, st, en))
    return cues
```
- [ ] Run → PASS. Commit.

---

### Task 4: `music.py` — `build_bed` (48 kHz/stereo, mood crossfades)

**Files:** Modify `src/pipeline/composer/music.py`; Test `tests/integration/test_music_bed.py`

**Filtergraph rule:** one looped input per cue. For cue *i*: `left_abut`/`right_abut` = previous/next cue end/start ≈ this cue's start/end (eps 1e-2). `place_at = start - XFADE if left_abut else start`; `seg_dur = end - place_at`; fade-in `d=XFADE if left_abut else EDGE` at `st=0`; fade-out `d=XFADE if right_abut else EDGE` at `st=seg_dur-d`. Place via `adelay`. Final `amix(normalize=0)` (skip amix if 1 cue) → `apad`/`atrim` to `total_sec`, forced `48000/stereo`.

- [ ] **Test first** (synthesize two mood tracks in tmp; assert bed duration + energy placement):
```python
import subprocess, json
from pathlib import Path
from pipeline.composer.music import build_bed, Cue, MoodTrack

def _tone(path, hz, sec=30):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"sine=frequency={hz}:duration={sec}",
                    "-ar","48000","-ac","2",str(path)], check=True, capture_output=True)

def _rms_db(path, ss, to):
    out = subprocess.run(["ffmpeg","-i",str(path),"-ss",str(ss),"-to",str(to),
        "-af","astats=metadata=1:reset=1","-f","null","-"],capture_output=True,text=True).stderr
    vals=[float(l.split(":")[-1]) for l in out.splitlines() if "RMS_level" in l and "Overall" not in l]
    return max(vals) if vals else -120.0

def test_build_bed_places_moods_and_silences_gaps(tmp_path):
    _tone(tmp_path/"tense.wav", 110); _tone(tmp_path/"hope.wav", 440)
    lib={"tense":MoodTrack("tense",tmp_path/"tense.wav"),"hopeful":MoodTrack("hopeful",tmp_path/"hope.wav")}
    cues=[Cue("tense",2.0,6.0), Cue("hopeful",6.0,10.0)]      # abutting → crossfade at 6.0
    bed=build_bed(cues, lib, total_sec=14.0, out_path=tmp_path/"bed.m4a")
    dur=float(subprocess.run(["ffprobe","-v","0","-show_entries","format=duration","-of","json",str(bed)],
        capture_output=True,text=True).stdout and json.loads(subprocess.run(["ffprobe","-v","0",
        "-show_entries","format=duration","-of","json",str(bed)],capture_output=True,text=True).stdout)["format"]["duration"])
    assert abs(dur-14.0) < 0.3                                  # full length
    assert _rms_db(bed,3.0,5.0) > -40                           # tense region audible
    assert _rms_db(bed,7.0,9.0) > -40                           # hopeful region audible
    assert _rms_db(bed,11.0,13.5) < -55                         # gap after last cue ~ silent
```
- [ ] **Implement** `build_bed(cues, library, total_sec, out_path) -> Path` — build input args (`-stream_loop -1 -i <track>` per cue), construct the per-cue filter strings per the rule above, join with the final amix/apad/atrim into `[bed]`, `run_ffmpeg(["ffmpeg","-y",*inputs,"-filter_complex",fc,"-map","[bed]","-ar","48000","-ac","2",str(out)])`. Return `out_path`.
- [ ] Run → PASS. Commit.

---

### Task 5: `music.py` — `duck_bed` (measurable) + `mux_music_onto_final`

**Files:** Modify `src/pipeline/composer/music.py`; Test `tests/integration/test_music_duck.py`

- [ ] **Test first** — duck keyed by a speech-then-silence track; assert ducking during speech + recovery in silence (relative contract; target 12–15 dB documented):
```python
import subprocess
from pipeline.composer.music import duck_bed
# reuse _tone/_rms_db helpers (copy into this test module)

def _speech_then_silence(path):  # 0-4s tone (speech), 4-8s silence
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=300:duration=4",
                    "-f","lavfi","-i","anullsrc=r=48000:cl=stereo:d=4",
                    "-filter_complex","[0:a][1:a]concat=n=2:v=0:a=1[a]","-map","[a]",
                    "-ar","48000","-ac","2",str(path)],check=True,capture_output=True)

def test_duck_reduces_under_speech_and_recovers(tmp_path):
    _tone(tmp_path/"bed.wav",220,8); _speech_then_silence(tmp_path/"key.wav")
    ducked=duck_bed(tmp_path/"bed.wav", tmp_path/"key.wav", tmp_path/"ducked.m4a", duck_db=15.0)
    speech=_rms_db(ducked,0.5,3.5); pause=_rms_db(ducked,4.5,7.5)
    assert pause - speech > 4.0          # recovers (louder) in pause vs under speech
    key_speech=_rms_db(tmp_path/"key.wav",0.5,3.5)
    assert key_speech - speech > 8.0     # bed sits well below speech while speaking
```
- [ ] **Implement:**
  - `duck_bed(bed_path, key_audio_path, out_path, duck_db=15.0) -> Path`: ffmpeg, inputs bed + key; filter `[1:a]aformat=sample_rates=48000:channel_layouts=stereo[k];[0:a]aformat=...,volume=-{duck_db}dB[m];[m][k]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[d]`; `-map [d] -ar 48000 -ac 2`. (Pre-`volume` sets resting floor; sidechain adds dynamic ducking under speech — both knobs make the speech/pause gap.) The ducked bed is a standalone artifact → directly measurable.
  - `mux_music_onto_final(final_video, narration_audio, ducked_bed, out_path) -> None`: `run_ffmpeg_atomic(["ffmpeg","-y","-i",final,"-i",narration,"-i",ducked,"-filter_complex","[1:a]aformat=...[n];[2:a]aformat=...[d];[n][d]amix=inputs=2:normalize=0:duration=first[mix]","-map","0:v","-c:v","copy","-map","[mix]","-c:a","aac","-b:a","192k",str(out)], out_path)`. Narration bus = input 1 = pristine `raw.mp4` → idempotent.
- [ ] Run → PASS. Commit.

---

### Task 6: CLI — `pipeline compose music`

**Files:** Modify `src/pipeline/cli_compose.py`; Test `tests/unit/test_cli_compose_music.py`

- [ ] **Implement** `@compose_app.command("music")` `def music(project_id, dry_run=False, duck_db=15.0)`:
  1. `work_dir=_resolve_work_dir(project_id)`; `ctx=PipelineContext.load(work_dir/"context.json")`; `sb=Storyboard.load(ctx.storyboard_path)`; `compose_dir=work_dir/"compose"`; `locale=ctx.locale`.
  2. `scenes=json.loads((compose_dir/"scenes.json").read_text())`; `cues=plan_cues(sb,scenes)`.
  3. **Short-circuit:** `if not cues: typer.echo("No music moods tagged — nothing to do."); return` (touches nothing).
  4. `library=load_library()`; **validate**: every `c.mood` has `library[mood].file.exists()` else `typer.echo(... err=True); raise typer.Exit(1)` (clear "missing bed for mood X — add it to assets/music/...").
  5. **`--dry-run`:** print each cue `mood [start,end) dur Ns → <track>`; return.
  6. `raw=compose_dir/"raw.mp4"`; `total=_get_duration_sec(raw)`; `music_dir=compose_dir/"music"`.
  7. `bed=build_bed(cues,library,total,music_dir/f"bed_{locale}.m4a")`; `ducked=duck_bed(bed,raw,music_dir/f"ducked_{locale}.m4a",duck_db)`.
  8. `finals=sorted(compose_dir.glob(f"final_{locale}_*.mp4"))`; for each `mux_music_onto_final(f, raw, ducked, f)`; echo each.
  9. `SessionEntry`/`append_session` like `reburn` (`command="compose music"`).
- [ ] **Test** (monkeypatch the three ffmpeg-touching fns; assert orchestration only):
```python
def test_music_short_circuits_when_no_moods(tmp_path, monkeypatch):
    # build a minimal work_dir (context.json, storyboard with no moods, scenes.json, raw.mp4 placeholder)
    # invoke via typer CliRunner; assert exit 0, output "nothing to do", and build_bed NOT called.
def test_music_errors_when_bed_missing(...):
    # storyboard tags s1=tense, library empty → exit code 1, message names the mood.
def test_music_dry_run_prints_plan_and_skips_render(...):
    # tags s1=tense + a fake library entry; --dry-run → prints cue, build_bed NOT called.
```
(Use `tests/unit/test_cli_compose.py` patterns for building a fake work_dir + `typer.testing.CliRunner`. Monkeypatch `pipeline.cli_compose.build_bed/duck_bed/mux_music_onto_final` and `load_library`.)
- [ ] Run → PASS. Commit.

---

### Task 7: Asset scaffolding + manifest (NO committed audio)

**Files:** Create `assets/music/{tense,somber,hopeful,triumphant,reflective}/.gitkeep`, `assets/music/library.json`, `assets/music/README.md`

- [ ] `library.json`: 5 mood entries, each `{"file":"", "title":"", "artist":"", "source":"YouTube Audio Library", "source_url":"", "license":"Attribution not required", "duration_s":0, "loudness_lufs":-20.0}`. Empty `file` ⇒ `load_library` skips it ⇒ CLI errors clearly if that mood is tagged. (No placeholder audio committed — real-track sourcing is Tim's step.)
- [ ] `README.md`: the per-mood selection criteria table (from the spec), the "attribution not required" rule, 48 kHz/stereo/≈−20 LUFS specs, and "drop a track in `<mood>/`, set its `file` + metadata in `library.json`."
- [ ] Commit.

---

### Task 8: Docs

**Files:** Modify `README.md` (Compose iteration block), `CLAUDE.md` (compose snippet)

- [ ] Add `uv run pipeline compose music --project-id <ID> [--dry-run]` with one line: "lays the mood music bed under narration; re-run after any reburn." Commit.

---

### Task 9: Verify

- [ ] `uv run pytest tests/unit/test_storyboard_music_mood.py tests/unit/test_music_resolve.py tests/unit/test_music_cues.py tests/integration/test_music_bed.py tests/integration/test_music_duck.py tests/unit/test_cli_compose_music.py -v` → all PASS.
- [ ] `uv run ruff check src/pipeline/composer/music.py src/pipeline/cli_compose.py src/pipeline/storyboard.py` → clean.
- [ ] `uv run mypy src/pipeline/composer/music.py` → clean.
- [ ] **Optional mechanics demo (only if useful, on a COPY):** `cp -r` the baby-walker `compose/` (raw.mp4, scenes.json, context.json, subtitle, final_*.mp4) + storyboard into a scratch `OUTPUT_DIR`; tag s19=tense/s22=hopeful/s24=none on the COPY's storyboard; synthesize throwaway beds into a temp library; run `compose music`. **This proves mechanics only — NOT the intelligibility acceptance** (needs real broadband tracks). Never touch the live project.
- [ ] Report: implemented + tests green; remaining human step = source 5 real YT-Audio-Library tracks into `assets/music/`. Do NOT merge — hand to EM REVIEW.

---

## Self-Review

- **Spec coverage:** schema (T1), library+manifest (T2 loader, T7 assets), mood resolution (T2), cue planning (T3), global bed + crossfade (T4), sidechain duck sourced from raw + amix mux (T5), CLI + dry-run + short-circuit + missing-bed error (T6), docs (T8), idempotency (raw-sourced mux, T5), 48 kHz/stereo (T4/T5), measurable ducked bed (T5). First-target arc validated by T3's fixture; real render is the optional/labeled T9 step. ✅
- **No placeholders:** test code + signatures + filtergraph rules are concrete; T6/T7 reference only fns defined in T2–T5.
- **Type consistency:** `Cue`, `MoodTrack`, `build_bed`/`duck_bed`/`mux_music_onto_final` signatures match across T4–T6.
