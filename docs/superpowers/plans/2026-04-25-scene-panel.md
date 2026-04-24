# Scene Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scene strip + narration panel to the dashboard video preview so the user always knows which scene is playing, can jump to any scene by clicking, and can copy-paste narration text for precise feedback.

**Architecture:** The compose stage accumulates real timestamps per scene and writes `compose/scenes.json` alongside each render. The scanner reads this file (or estimates from `storyboard.json` as fallback) and passes a `scenes` array through the API. The dashboard frontend renders chips below the video, tracks `currentTime` to highlight the active chip, and shows selectable narration on click.

**Tech Stack:** Python dataclasses, FastAPI, vanilla JS/HTML/CSS

---

## File Map

| File | Change |
|---|---|
| `src/pipeline/stages/compose.py` | Accumulate timestamps in scene loop; write `compose/scenes.json` |
| `src/pipeline/dashboard/scanner.py` | Add `scenes` field to `ProjectInfo`; read `scenes.json` or estimate from storyboard |
| `src/pipeline/dashboard/server.py` | Pass `scenes` through `_to_dict` |
| `src/pipeline/dashboard/static/index.html` | Scene strip CSS + HTML + JS |
| `tests/unit/test_dashboard_scanner.py` | 3 new tests for scenes loading |
| `tests/unit/test_dashboard_server.py` | 1 new test for `scenes` in API response |
| `tests/unit/test_compose_v2.py` | 1 new test for `scenes.json` written by compose |

---

## Task 1: Scanner — `scenes` field + storyboard fallback

**Files:**
- Modify: `src/pipeline/dashboard/scanner.py`
- Modify: `tests/unit/test_dashboard_scanner.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_dashboard_scanner.py`:

```python
def test_scenes_empty_when_no_storyboard(tmp_path: Path) -> None:
    _make_project(tmp_path, "2001")
    [p] = scan_projects(tmp_path / "output")
    assert p.scenes == []


def test_scenes_loaded_from_scenes_json(tmp_path: Path) -> None:
    scenes = [
        {"id": "s1", "section": "hook", "start_sec": 0.0, "duration_sec": 5.0, "narration": "Hello"},
        {"id": "s2", "section": "context", "start_sec": 5.0, "duration_sec": 8.0, "narration": "World"},
    ]
    project_dir = _make_project(tmp_path, "2002")
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "scenes.json").write_text(json.dumps(scenes))
    [p] = scan_projects(tmp_path / "output")
    assert p.scenes == scenes


def test_scenes_estimated_from_storyboard_fallback(tmp_path: Path) -> None:
    storyboard = {
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "First", "narration_est_sec": 10.0, "pause_after_sec": 0.5},
            {"id": "s2", "section": "context", "narration": "Second", "narration_est_sec": 20.0, "pause_after_sec": 0.0},
        ]
    }
    project_dir = _make_project(tmp_path, "2003")
    (project_dir / "storyboard.json").write_text(json.dumps(storyboard))
    [p] = scan_projects(tmp_path / "output")
    assert len(p.scenes) == 2
    assert p.scenes[0] == {"id": "s1", "section": "hook", "start_sec": 0.0, "duration_sec": 10.5, "narration": "First"}
    assert p.scenes[1] == {"id": "s2", "section": "context", "start_sec": 10.5, "duration_sec": 20.0, "narration": "Second"}


def test_scenes_json_takes_priority_over_storyboard(tmp_path: Path) -> None:
    scenes_json = [{"id": "s1", "section": "hook", "start_sec": 0.0, "duration_sec": 5.0, "narration": "From file"}]
    storyboard = {"scenes": [{"id": "s1", "section": "hook", "narration": "From storyboard", "narration_est_sec": 99.0, "pause_after_sec": 0}]}
    project_dir = _make_project(tmp_path, "2004")
    (project_dir / "storyboard.json").write_text(json.dumps(storyboard))
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "scenes.json").write_text(json.dumps(scenes_json))
    [p] = scan_projects(tmp_path / "output")
    assert p.scenes[0]["narration"] == "From file"
    assert p.scenes[0]["duration_sec"] == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_dashboard_scanner.py::test_scenes_empty_when_no_storyboard tests/unit/test_dashboard_scanner.py::test_scenes_loaded_from_scenes_json tests/unit/test_dashboard_scanner.py::test_scenes_estimated_from_storyboard_fallback tests/unit/test_dashboard_scanner.py::test_scenes_json_takes_priority_over_storyboard -v
```

Expected: 4 FAILED (AttributeError or similar — `scenes` field not on `ProjectInfo`)

- [ ] **Step 3: Implement `scenes` field + loading logic**

In `src/pipeline/dashboard/scanner.py`:

1. Add `scenes` to the `ProjectInfo` dataclass after `session_logs`:

```python
scenes: list[dict[str, object]] = field(default_factory=list)
```

2. Add `_estimate_scenes_from_storyboard` after `_find_all_final_videos`:

```python
def _estimate_scenes_from_storyboard(sb_path: Path) -> list[dict[str, object]]:
    with contextlib.suppress(json.JSONDecodeError, OSError):
        data = json.loads(sb_path.read_text(encoding="utf-8"))
        start = 0.0
        result: list[dict[str, object]] = []
        for scene in data.get("scenes", []):
            dur = float(scene.get("narration_est_sec", 0)) + float(scene.get("pause_after_sec", 0))
            result.append({
                "id": scene["id"],
                "section": scene.get("section", ""),
                "start_sec": start,
                "duration_sec": dur,
                "narration": scene.get("narration", ""),
            })
            start += dur
        return result
    return []
```

3. In `scan_projects`, after the `session_logs` block and before `results.append(...)`, add:

```python
scenes: list[dict[str, object]] = []
scenes_file = project_dir / "compose" / "scenes.json"
if scenes_file.exists():
    with contextlib.suppress(json.JSONDecodeError, OSError):
        scenes = json.loads(scenes_file.read_text(encoding="utf-8"))
elif (project_dir / "storyboard.json").exists():
    scenes = _estimate_scenes_from_storyboard(project_dir / "storyboard.json")
```

4. Add `scenes=scenes,` to the `ProjectInfo(...)` constructor call.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_dashboard_scanner.py::test_scenes_empty_when_no_storyboard tests/unit/test_dashboard_scanner.py::test_scenes_loaded_from_scenes_json tests/unit/test_dashboard_scanner.py::test_scenes_estimated_from_storyboard_fallback tests/unit/test_dashboard_scanner.py::test_scenes_json_takes_priority_over_storyboard -v
```

Expected: 4 PASSED

- [ ] **Step 5: Run full scanner test suite**

```bash
uv run pytest tests/unit/test_dashboard_scanner.py -v
```

Expected: all PASSED (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/dashboard/scanner.py tests/unit/test_dashboard_scanner.py
git commit -m "feat(scanner): add scenes field with scenes.json / storyboard fallback"
```

---

## Task 2: Server — pass `scenes` through API

**Files:**
- Modify: `src/pipeline/dashboard/server.py`
- Modify: `tests/unit/test_dashboard_server.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_dashboard_server.py`:

```python
def test_api_projects_includes_scenes(tmp_path: Path) -> None:
    output_dir = _output_dir(tmp_path)
    project_dir = output_dir / "projects" / "7777"
    project_dir.mkdir(parents=True)
    (project_dir / "context.json").write_text(json.dumps({
        "project_id": "7777",
        "locale": "zh-TW",
        "source_url": None,
        "niche": None,
        "youtube_video_id": None,
        "published_at": None,
    }))
    scenes = [{"id": "s1", "section": "hook", "start_sec": 0.0, "duration_sec": 5.0, "narration": "Hello"}]
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "scenes.json").write_text(json.dumps(scenes))

    client = TestClient(create_app(output_dir))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    [p] = resp.json()
    assert p["scenes"] == scenes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_dashboard_server.py::test_api_projects_includes_scenes -v
```

Expected: FAILED (KeyError or `scenes` key missing)

- [ ] **Step 3: Add `scenes` to `_to_dict`**

In `src/pipeline/dashboard/server.py`, in `_to_dict`, add after `"session_logs"`:

```python
"scenes": p.scenes,
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_dashboard_server.py::test_api_projects_includes_scenes -v
```

Expected: PASSED

- [ ] **Step 5: Run full server test suite**

```bash
uv run pytest tests/unit/test_dashboard_server.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/unit/test_dashboard_server.py
git commit -m "feat(server): pass scenes array through API response"
```

---

## Task 3: Compose stage — write `compose/scenes.json`

**Files:**
- Modify: `src/pipeline/stages/compose.py`
- Modify: `tests/unit/test_compose_v2.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_compose_v2.py`:

```python
import json

def test_scenes_json_written_by_storyboard_compose(monkeypatch, tmp_path):
    """After _compose_from_storyboard, compose/scenes.json exists with correct timestamps."""
    from pathlib import Path
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    storyboard = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="First scene", narration_est_sec=5.0,
                  visual={"type": "text_card", "text": "hi"}, pause_after_sec=0.5),
            Scene(id="s2", section="context", narration="Second scene", narration_est_sec=8.0,
                  visual={"type": "text_card", "text": "ho"}, pause_after_sec=0.0),
        ]
    )
    sb_path = work_dir / "storyboard.json"
    storyboard.save(sb_path)

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        narration_path=narration,
        subtitle_path=subs,
        storyboard_path=sb_path,
        segment_timings=[
            {"index": 0, "text": "First scene", "path": str(narration), "start_ms": 0, "duration_ms": 5000},
            {"index": 1, "text": "Second scene", "path": str(narration), "start_ms": 5000, "duration_ms": 8000},
        ],
        burn_subtitles=False,
    )

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg",
        lambda cmd: Path(cmd[-1]).write_bytes(b"mp4"))
    monkeypatch.setattr("pipeline.stages.compose.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pipeline.stages.compose.render_scene",
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    import asyncio
    asyncio.run(ComposeStage().run(ctx))

    scenes_file = work_dir / "compose" / "scenes.json"
    assert scenes_file.exists(), "compose/scenes.json was not written"
    scenes = json.loads(scenes_file.read_text())
    assert len(scenes) == 2

    assert scenes[0]["id"] == "s1"
    assert scenes[0]["section"] == "hook"
    assert scenes[0]["start_sec"] == 0.0
    assert scenes[0]["duration_sec"] == pytest.approx(5.5)   # 5000ms + 0.5s pause
    assert scenes[0]["narration"] == "First scene"

    assert scenes[1]["id"] == "s2"
    assert scenes[1]["start_sec"] == pytest.approx(5.5)
    assert scenes[1]["duration_sec"] == pytest.approx(8.0)   # 8000ms + 0s pause
    assert scenes[1]["narration"] == "Second scene"
```

Add `import pytest` at the top of `test_compose_v2.py` (it is not there yet):

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_compose_v2.py::test_scenes_json_written_by_storyboard_compose -v
```

Expected: FAILED (`compose/scenes.json` not found)

- [ ] **Step 3: Implement timestamp accumulation and `scenes.json` write**

In `src/pipeline/stages/compose.py`, in `_compose_from_storyboard`:

1. Before the scene loop (around line 114, before `scene_finals: list[Path] = []`), add:

```python
scenes_data: list[dict[str, object]] = []
_running_sec = 0.0
```

2. At the end of the scene loop body — after the pause block (after `scene_finals.append(pause_path)` at the end of step 4, around line 260) — add:

```python
scene_dur = duration + scene.pause_after_sec
scenes_data.append({
    "id": scene.id,
    "section": scene.section,
    "start_sec": _running_sec,
    "duration_sec": scene_dur,
    "narration": scene.narration,
})
_running_sec += scene_dur
```

3. After the scene loop (between the loop closing and `# Step 5: Concatenate`, around line 262), add:

```python
(compose_dir / "scenes.json").write_text(
    json.dumps(scenes_data, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_compose_v2.py::test_scenes_json_written_by_storyboard_compose -v
```

Expected: PASSED

- [ ] **Step 5: Run full compose test suite**

```bash
uv run pytest tests/unit/test_compose_v2.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/compose.py tests/unit/test_compose_v2.py
git commit -m "feat(compose): write scenes.json with real timestamps after each render"
```

---

## Task 4: Frontend — scene strip + narration panel

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html`

No automated JS tests. Verify manually using the dashboard after changes.

- [ ] **Step 1: Add CSS for scene strip and narration panel**

In `index.html`, add inside the `<style>` block after the `.btn-variant` rule (around line 62):

```css
    .scene-strip { display:flex; gap:5px; overflow-x:auto; padding:10px 0 6px; scrollbar-width:thin; scroll-behavior:smooth; }
    .scene-chip { flex-shrink:0; padding:4px 10px; border-radius:4px; font-size:10px; font-family:monospace;
      cursor:pointer; background:#1e1e1e; color:#4a5568; border:1px solid #2d3748;
      white-space:nowrap; transition:background .1s, color .1s; }
    .scene-chip:hover { background:#1e293b; color:#94a3b8; }
    .scene-chip.sc-past { background:#161616; color:#374151; border-color:#161616; }
    .scene-chip.sc-active { background:#1e3a5f; color:#93c5fd; border-color:#3b82f6; }
    .scene-narration { margin-top:2px; background:#1e293b; border:1px solid #334155; border-radius:6px;
      padding:10px 14px; font-size:12px; color:#cbd5e1; line-height:1.7; user-select:text; cursor:text;
      margin-bottom:10px; }
    .scene-nar-hdr { font-size:10px; color:#6366f1; font-family:monospace; margin-bottom:6px; }
```

- [ ] **Step 2: Add `buildSceneStrip` helper function**

In `index.html`, add this function in the `<script>` block after `makeDetailRow`:

```javascript
function buildSceneStrip(scenes) {
  const chips = scenes.map((s, i) =>
    `<div class="scene-chip" data-idx="${i}" data-start="${s.start_sec}">${s.id} · ${s.section}</div>`
  ).join('');
  return `
    <div class="scene-strip">${chips}</div>
    <div class="scene-narration" style="display:none">
      <div class="scene-nar-hdr"></div>
      <div class="scene-nar-text"></div>
    </div>`;
}
```

- [ ] **Step 3: Insert scene strip into `makeDetailRow`**

In `makeDetailRow`, the `dr.innerHTML` string contains `<video controls src="${firstUrl}"></video>`. Add the scene strip immediately after the video tag:

```javascript
    <video controls src="${firstUrl}"></video>
    ${p.scenes && p.scenes.length ? buildSceneStrip(p.scenes) : ''}
```

The existing line in `makeDetailRow` is:

```javascript
    <video controls src="${firstUrl}"></video>
```

Change it to:

```javascript
    <video controls src="${firstUrl}"></video>
    ${p.scenes && p.scenes.length ? buildSceneStrip(p.scenes) : ''}
```

Everything else in `dr.innerHTML` stays unchanged.

- [ ] **Step 4: Wire `timeupdate` and chip click events**

In `toggleDetail`, after `tr?.insertAdjacentElement('afterend', detailRow)` and the existing variant-tab wiring block, add:

```javascript
  // Wire scene strip
  const vid = detailRow.querySelector('video');
  const strip = detailRow.querySelector('.scene-strip');
  if (vid && strip && p.scenes && p.scenes.length) {
    let activeSc = -1;
    vid.addEventListener('timeupdate', () => {
      const t = vid.currentTime;
      let idx = 0;
      for (let i = 0; i < p.scenes.length; i++) {
        if (t >= p.scenes[i].start_sec) idx = i;
      }
      if (idx === activeSc) return;
      activeSc = idx;
      strip.querySelectorAll('.scene-chip').forEach((c, i) => {
        c.classList.toggle('sc-past', i < idx);
        c.classList.toggle('sc-active', i === idx);
      });
      strip.querySelectorAll('.scene-chip')[idx]?.scrollIntoView({inline: 'nearest', behavior: 'smooth'});
    });

    let openSc = -1;
    strip.addEventListener('click', e => {
      const chip = e.target.closest('.scene-chip');
      if (!chip) return;
      const idx = +chip.dataset.idx;
      const scene = p.scenes[idx];
      vid.currentTime = scene.start_sec;
      const narPanel = detailRow.querySelector('.scene-narration');
      const narHdr   = detailRow.querySelector('.scene-nar-hdr');
      const narText  = detailRow.querySelector('.scene-nar-text');
      if (openSc === idx) {
        narPanel.style.display = 'none';
        openSc = -1;
      } else {
        const mm = Math.floor(scene.start_sec / 60);
        const ss = String(Math.floor(scene.start_sec % 60)).padStart(2, '0');
        narHdr.textContent = `${scene.id} · ${scene.section} · ${mm}:${ss}`;
        narText.textContent = scene.narration;
        narPanel.style.display = 'block';
        openSc = idx;
      }
    });
  }
```

- [ ] **Step 5: Clear scene strip state on variant switch**

In the existing variant-tab click handler (the `detailRow.querySelectorAll('.btn-variant').forEach(btn => { btn.addEventListener('click', ...) })` block in `toggleDetail`), add strip reset after `vid.load(); vid.play()`:

```javascript
    btn.addEventListener('click', () => {
      const vid = detailRow.querySelector('video');
      if (vid) { vid.src = btn.dataset.url; vid.load(); vid.play(); }
      detailRow.querySelectorAll('.btn-variant').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      // Reset scene strip — timeupdate will re-sync once video loads
      detailRow.querySelectorAll('.scene-chip').forEach(c => c.classList.remove('sc-active', 'sc-past'));
      const narPanel = detailRow.querySelector('.scene-narration');
      if (narPanel) narPanel.style.display = 'none';
    });
```

- [ ] **Step 6: Manual verification**

Start the dashboard and open a rendered project:

```bash
./scripts/start-dashboard.sh --local-only
```

Check:
1. Open a project that has `compose/scenes.json` (re-run compose on any project, or create a test one) → scene strip appears below video
2. Press play → active chip advances and scrolls into view
3. Click a chip → video jumps to that scene; narration panel opens below strip with selectable text
4. Click same chip again → narration panel closes
5. Click different chip → previous panel closes, new one opens
6. Switch variant tab → strip resets (no highlighted chip), narration closes
7. Open a project without scenes (storyboard-only status) → no strip rendered, layout unchanged

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): scene strip with narration panel for video preview"
```

---

## Task 5: Run full test suite and clean up

- [ ] **Step 1: Run all unit tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all PASSED

- [ ] **Step 2: Run linter**

```bash
uv run ruff check src/pipeline/stages/compose.py src/pipeline/dashboard/scanner.py src/pipeline/dashboard/server.py
```

Expected: no errors

- [ ] **Step 3: Final commit if any lint fixes needed**

```bash
git add -p
git commit -m "fix: ruff lint fixes for scene panel"
```
