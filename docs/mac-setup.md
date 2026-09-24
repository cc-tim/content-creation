# Mac workshop setup (two-machine workflow)

Two machines share this project (decided 2026-09-24, roadmap epic E8):

| Machine | Role | Always on? |
|---|---|---|
| **Hub** — Linux box `tim-huang-gaming-b8` (i5-7400, GTX 1050) | Dashboard, tunnel, Telegram, discovery, **publish**, YouTube tokens, overnight final renders | Yes |
| **Workshop** — M3 MacBook Pro | Development, tests, fast iteration renders (preview *and* full when you want a result quickly) | Daytime |

**Rules**
1. Code moves only through git (GitHub `cc-tim/content-creation`). Never rsync code.
2. Project data (`output/projects/<id>`) moves by copy. One machine owns a project at a time.
3. Publish always happens from the hub (it holds the YouTube tokens).

Hub storage: repo `output/` is a symlink to `/mnt/windows_ssd/content-creation/output`
(SSD data volume, marker `.content-creation-volume`). Code stays at `/home/tim-huang/content-creation`.

## One-time Mac setup

```bash
# 1. System tools
brew install git gh uv ffmpeg rsync
brew install --cask font-noto-sans-cjk font-noto-serif-cjk   # CJK fonts the renderer needs
fc-cache -f                                                   # refresh fontconfig so ffmpeg sees them
ffmpeg -hide_banner -encoders | grep videotoolbox             # expect h264_videotoolbox
# The renderer needs an ffmpeg with libfreetype + libfontconfig + libass (drawtext and
# subtitles filters). If step 8 reports one missing: `brew install ffmpeg-full` and put it
# first on PATH (it may be keg-only, e.g. export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
# in ~/.zshrc). Record which ffmpeg you ended up with.

# 2. SSH alias for the hub (over Tailscale)
cat >> ~/.ssh/config <<'EOF'
Host hub
  HostName tim-huang-gaming-b8
  User tim-huang
EOF
ssh hub 'echo ok'                                             # add your Mac key to hub authorized_keys if this prompts

# 3. Code
gh auth login                                                 # as cc-tim
git clone https://github.com/cc-tim/content-creation.git ~/content-creation
cd ~/content-creation && uv sync

# 4. Secrets (never committed) — copy from the hub
scp hub:content-creation/.env ~/content-creation/.env
mkdir -p ~/.claude && scp hub:.claude/api-keys.json ~/.claude/api-keys.json

# 4b. Home-dir media tools (not in git) — copy from the hub. Without gen-image.py and
#     keymanager.py every image generation fails and rich_slide backgrounds quietly fall
#     back to flat; gen-image-edit.py is used by the fit-image/refit path.
mkdir -p ~/.claude/bin
scp 'hub:.claude/bin/{gen-image.py,gen-image-edit.py,keymanager.py}' ~/.claude/bin/
chmod +x ~/.claude/bin/*.py

# 5. Optional: wiki-explainer sources (raw/ symlink target)
git clone git@github.com:timhuang1018/know-fountains.git ~/know-fountains
ln -s ../know-fountains/raw ~/content-creation/raw

# 6. Claude Code project plugin (inside a Claude Code session in ~/content-creation)
#   /plugin marketplace add ~/content-creation
#   /plugin install content-creation@content-creation-local

# 7. Sanity check (golden-PNG compares are SKIPPED off-Linux with a "hub-canonical" reason)
uv run pytest -q -rs

# 8. Render readiness: fonts, fontconfig, ffmpeg capabilities, CJK glyph probes, home tools
uv run pipeline doctor --out tmp/e8-fonts/mac ; echo "exit=$?"   # expect exit=0, every line PASS
```

YouTube OAuth tokens are **not** copied — publish stays on the hub.

## Moving a project between machines (manual, until E8 item 2 ships)

The hub volume is NTFS, so rsync skips permissions/owners and tolerates 2 s timestamp drift.

```bash
ID=<project-id>
HUBP=/mnt/windows_ssd/content-creation/output/projects

# Check out to the Mac: mark the hub copy, then pull
ssh hub "echo mac \$(date -Is) > $HUBP/$ID/.checked-out"
rsync -rlt --modify-window=2 --exclude .checked-out hub:$HUBP/$ID/ ~/content-creation/output/projects/$ID/

# ... work, render on the Mac ...

# Check in to the hub: push back, then clear the mark
rsync -rlt --no-perms --no-owner --no-group --modify-window=2 --exclude .checked-out \
  ~/content-creation/output/projects/$ID/ hub:$HUBP/$ID/
ssh hub "rm $HUBP/$ID/.checked-out"
```

While `.checked-out` exists on the hub, do not edit or render that project on the hub.
(E8 item 2 replaces this with `pipeline project checkout/checkin` and a dashboard-visible lock.)

## Rendering on the Mac

- Fonts resolve through one resolver (`src/pipeline/utils/fonts.py`, E8 item 1): Noto
  {Sans,Serif} CJK TC found by name, no substitute font. A missing font fails loudly with
  the install command, and `uv run pipeline doctor` checks everything a render needs.
- **First time after E8 item 1 merges: run the Mac verification below** and send the
  evidence (B1–B6) to the engineering-manager so the sprint can flip to done.
- Preview renders (E8 item 3) will use `h264_videotoolbox` on the Mac and `h264_nvenc` on the
  hub (GTX 1050; measured ~4.5× faster than libx264 medium at 1080p). Finals stay libx264.

## Mac verification for E8 item 1 (fonts)

From the sprint spec (`docs/superpowers/specs/2026-09-24-e8-cross-platform-fonts-design.md`,
section 8B). Run once on the M3 right after the merge.

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

Evidence to send back: B1 step-1 output; B2 doctor stdout + `tmp/e8-fonts/mac/*.png` probes;
B3 `pytest -q -rs` tail (0 failed, 0 errors, only hub-canonical golden skips + pre-existing
skips); B4 the `--integration` CJK test passing; B5 s11/s31/s24 frames next to the hub
`tmp/e8-fonts/hub/` renders (real TC glyphs, Noto look, same layout); B6 (informational) the
`PIPELINE_GOLDEN_STRICT=1` result.

## Daily rhythm

| When | Where | What |
|---|---|---|
| Morning | Mac | `git pull`, check out the project |
| Day | Mac | Edit → render → review; build tools in worktrees |
| Evening | Mac → hub | Push code, check in the project; queue slow jobs on the hub |
| Night | Hub | Final renders, discovery |
| Next morning | Phone / dashboard | Review, then publish from the hub |
