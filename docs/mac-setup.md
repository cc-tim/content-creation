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
ffmpeg -hide_banner -encoders | grep videotoolbox             # expect h264_videotoolbox

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

# 5. Optional: wiki-explainer sources (raw/ symlink target)
git clone git@github.com:timhuang1018/know-fountains.git ~/know-fountains
ln -s ../know-fountains/raw ~/content-creation/raw

# 6. Claude Code project plugin (inside a Claude Code session in ~/content-creation)
#   /plugin marketplace add ~/content-creation
#   /plugin install content-creation@content-creation-local

# 7. Sanity check
uv run pytest -q
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

- **Blocked until E8 item 1 merges**: font paths are Linux-only today, so CJK text would
  render wrong or blank. After it merges, run the Mac verification steps in the sprint spec.
- Preview renders (E8 item 3) will use `h264_videotoolbox` on the Mac and `h264_nvenc` on the
  hub (GTX 1050; measured ~4.5× faster than libx264 medium at 1080p). Finals stay libx264.

## Daily rhythm

| When | Where | What |
|---|---|---|
| Morning | Mac | `git pull`, check out the project |
| Day | Mac | Edit → render → review; build tools in worktrees |
| Evening | Mac → hub | Push code, check in the project; queue slow jobs on the hub |
| Night | Hub | Final renders, discovery |
| Next morning | Phone / dashboard | Review, then publish from the hub |
