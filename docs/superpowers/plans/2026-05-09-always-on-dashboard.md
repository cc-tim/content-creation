# Always-On Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the content dashboard permanently accessible at a stable HTTPS URL with Google auth, auto-restarting only when AI agent sessions end with code changes in `src/pipeline/`.

**Architecture:** Two systemd user services (dashboard + cloudflared named tunnel) survive reboots; a shared shell script hooked into Claude Code and Codex `Stop` events detects `git status` changes and conditionally restarts the dashboard service; Cloudflare Access gates the public URL with Google OAuth.

**Tech Stack:** systemd user services, cloudflared Named Tunnel, Cloudflare Zero Trust Access, bash, jq, Claude Code hooks (`~/.claude/settings.json`), Codex hooks (`~/.codex/hooks.json`).

**Spec:** `docs/superpowers/specs/2026-05-09-always-on-dashboard-design.md`

---

## File Map

| Action | Path |
|---|---|
| Create | `scripts/restart-dashboard-if-changed.sh` |
| Modify | `~/.claude/settings.json` (append to existing Stop array) |
| Create | `~/.codex/hooks.json` |
| Create | `~/.config/systemd/user/content-dashboard.service` |
| Create | `~/.config/systemd/user/cloudflared-named-tunnel.service` |
| Create | `~/.cloudflared/config.yml` (after tunnel is created in Task 5) |

---

## Task 1: Create the hook script

**Files:**
- Create: `scripts/restart-dashboard-if-changed.sh`

- [ ] **Step 1: Write the script**

```bash
cat > /home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh << 'EOF'
#!/usr/bin/env bash
# Restart content dashboard when an AI agent session ends with src/pipeline/ changes.
# Called by Claude Code and Codex Stop hooks. Always exits 0 (non-blocking).

PROJECT_DIR="/home/tim-huang/content-creation"

CHANGED=$(git -C "$PROJECT_DIR" status --porcelain src/pipeline/ 2>/dev/null || true)

if [[ -n "$CHANGED" ]]; then
  systemctl --user restart content-dashboard 2>/dev/null || true
fi

exit 0
EOF
chmod +x /home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh
```

- [ ] **Step 2: Verify it is executable and runs cleanly**

```bash
/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh
echo "exit code: $?"
```

Expected: no output, exit code 0. (Service restart will fail silently since the service doesn't exist yet — that's fine.)

- [ ] **Step 3: Verify no-change path (repo must be clean for this test)**

```bash
git -C /home/tim-huang/content-creation status --porcelain src/pipeline/
```

Expected: empty output (no changes to detect).

- [ ] **Step 4: Commit**

```bash
git -C /home/tim-huang/content-creation add scripts/restart-dashboard-if-changed.sh
git -C /home/tim-huang/content-creation commit -m "feat(infra): add stop-hook script to restart dashboard on pipeline changes"
```

---

## Task 2: Merge Claude Code Stop hook

**Files:**
- Modify: `~/.claude/settings.json`

The file already has a `Stop` array with one entry (`stop-upload.py`). Append — do not overwrite.

- [ ] **Step 1: Verify current Stop array**

```bash
jq '.hooks.Stop' ~/.claude/settings.json
```

Expected: array with one entry whose command is `/home/tim-huang/.claude/hooks/stop-upload.py`.

- [ ] **Step 2: Append the new hook using jq**

```bash
jq '.hooks.Stop += [{"hooks": [{"type": "command", "command": "/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh", "timeout": 10}]}]' \
  ~/.claude/settings.json > /tmp/claude-settings-new.json \
  && mv /tmp/claude-settings-new.json ~/.claude/settings.json
```

- [ ] **Step 3: Verify the Stop array now has two entries**

```bash
jq '.hooks.Stop | length' ~/.claude/settings.json
```

Expected: `2`

```bash
jq '.hooks.Stop[-1].hooks[0].command' ~/.claude/settings.json
```

Expected: `"/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh"`

---

## Task 3: Configure Codex Stop hook

**Files:**
- Create: `~/.codex/hooks.json`

- [ ] **Step 1: Write the hooks file**

```bash
cat > ~/.codex/hooks.json << 'EOF'
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
EOF
```

- [ ] **Step 2: Verify valid JSON**

```bash
jq . ~/.codex/hooks.json
```

Expected: pretty-printed JSON with no errors.

---

## Task 4: Create content-dashboard systemd service

**Files:**
- Create: `~/.config/systemd/user/content-dashboard.service`

- [ ] **Step 1: Write the service file**

```bash
cat > ~/.config/systemd/user/content-dashboard.service << 'EOF'
[Unit]
Description=Content Creation Dashboard
After=network.target

[Service]
WorkingDirectory=/home/tim-huang/content-creation
ExecStart=/home/tim-huang/.local/bin/uv run pipeline dashboard --no-browser --port 8765
Restart=on-failure
RestartSec=5
StandardOutput=append:/tmp/dashboard-8765.log
StandardError=append:/tmp/dashboard-8765.log
Environment=HOME=/home/tim-huang
Environment=PATH=/home/tim-huang/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF
```

- [ ] **Step 2: Reload systemd user daemon**

```bash
systemctl --user daemon-reload
```

- [ ] **Step 3: Verify the unit file parses without errors**

```bash
systemctl --user cat content-dashboard.service
```

Expected: prints the unit file back with no errors.

---

## Task 5: Cloudflare Named Tunnel one-time setup

**Files:**
- Create: `~/.cloudflared/config.yml` (after tunnel ID is known)

This task has manual sub-steps requiring a browser. Have your Cloudflare account ready.

- [ ] **Step 1: Authenticate cloudflared with your Cloudflare account**

```bash
~/.local/bin/cloudflared login
```

This opens a browser. Select your domain (the one you want `dashboard.<your-domain>` on). After authenticating, `~/.cloudflared/cert.pem` is created.

- [ ] **Step 2: Create the named tunnel**

```bash
~/.local/bin/cloudflared tunnel create content-dashboard
```

Expected output ends with a line like:
```
Created tunnel content-dashboard with id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Note the tunnel ID — you will use it in the next step.

- [ ] **Step 3: Verify credentials file was created**

```bash
ls ~/.cloudflared/*.json
```

Expected: one file named `<tunnel-id>.json`.

- [ ] **Step 4: Write the tunnel config file**

Replace `<tunnel-id>` with the actual UUID from Step 2, and `<your-domain>` with your domain:

```bash
TUNNEL_ID=$(~/.local/bin/cloudflared tunnel list --output json | jq -r '.[] | select(.name=="content-dashboard") | .id')
DOMAIN="<your-domain>"   # e.g. example.com

cat > ~/.cloudflared/config.yml << EOF
tunnel: ${TUNNEL_ID}
credentials-file: /home/tim-huang/.cloudflared/${TUNNEL_ID}.json
ingress:
  - hostname: dashboard.${DOMAIN}
    service: http://localhost:8765
  - service: http_status:404
EOF
```

- [ ] **Step 5: Verify config renders correctly**

```bash
cat ~/.cloudflared/config.yml
```

Expected: `tunnel:` line shows the UUID, `hostname:` line shows `dashboard.<your-domain>`.

- [ ] **Step 6: Create the DNS CNAME record**

```bash
~/.local/bin/cloudflared tunnel route dns content-dashboard dashboard.<your-domain>
```

Expected: `INF Added CNAME dashboard.<your-domain> which will route to this tunnel tunnelID=...`

- [ ] **Step 7: Verify the tunnel configuration is valid**

```bash
~/.local/bin/cloudflared tunnel ingress validate
```

Expected: `Validating rules from /home/tim-huang/.cloudflared/config.yml` followed by `OK`.

---

## Task 6: Create cloudflared-named-tunnel systemd service

**Files:**
- Create: `~/.config/systemd/user/cloudflared-named-tunnel.service`

This task requires Task 5 (named tunnel + config.yml) to be complete first.

- [ ] **Step 1: Write the service file**

```bash
cat > ~/.config/systemd/user/cloudflared-named-tunnel.service << 'EOF'
[Unit]
Description=Cloudflare Named Tunnel (content dashboard)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/tim-huang/.local/bin/cloudflared tunnel run content-dashboard
Restart=always
RestartSec=10
Environment=HOME=/home/tim-huang

[Install]
WantedBy=default.target
EOF
```

- [ ] **Step 2: Reload systemd user daemon**

```bash
systemctl --user daemon-reload
```

- [ ] **Step 3: Verify the unit file parses**

```bash
systemctl --user cat cloudflared-named-tunnel.service
```

Expected: prints the unit file with no errors.

---

## Task 7: Enable and start both services

- [ ] **Step 1: Enable and start the dashboard service**

```bash
systemctl --user enable --now content-dashboard.service
```

- [ ] **Step 2: Wait 5 seconds, then verify it is running**

```bash
sleep 5 && systemctl --user status content-dashboard.service --no-pager
```

Expected: `Active: active (running)`. If it failed, check `/tmp/dashboard-8765.log`.

- [ ] **Step 3: Verify the dashboard API responds**

```bash
curl -s http://localhost:8765/api/projects | head -c 100
```

Expected: JSON starting with `[` or `{}` (not an error).

- [ ] **Step 4: Enable and start the tunnel service**

```bash
systemctl --user enable --now cloudflared-named-tunnel.service
```

- [ ] **Step 5: Wait 10 seconds, then verify the tunnel is running**

```bash
sleep 10 && systemctl --user status cloudflared-named-tunnel.service --no-pager
```

Expected: `Active: active (running)`.

- [ ] **Step 6: Check tunnel is connected to Cloudflare**

```bash
journalctl --user -u cloudflared-named-tunnel.service --no-pager -n 20
```

Expected: lines containing `Connection` and `Registered tunnel connection` with no fatal errors.

- [ ] **Step 7: Add dashrs shell alias for manual restarts**

Append to `~/.bashrc` (or `~/.zshrc` if using zsh):

```bash
echo "alias dashrs='systemctl --user restart content-dashboard'" >> ~/.bashrc
source ~/.bashrc
```

Verify: `type dashrs` → `dashrs is aliased to 'systemctl --user restart content-dashboard'`

---

## Task 8: Cloudflare Access setup (manual web UI)

This task is done entirely in the Cloudflare dashboard browser UI. No terminal commands.

- [ ] **Step 1: Open Cloudflare Zero Trust**

Go to https://one.dash.cloudflare.com → select your account.

- [ ] **Step 2: Create a new Access application**

Navigate: Access → Applications → Add an application → Self-hosted.

- [ ] **Step 3: Configure the application**

- **Application name:** `Content Dashboard`
- **Application domain:** `dashboard.<your-domain>` (must match the CNAME from Task 5 Step 6)
- Leave session duration at default (24 hours is fine)

Click Next.

- [ ] **Step 4: Add an Allow policy**

- **Policy name:** `Owner only`
- **Action:** Allow
- **Include rule:** Selector = `Emails`, Value = `t8522192@gmail.com`

Click Next → Save.

- [ ] **Step 5: Verify the application appears in the list**

Access → Applications — `Content Dashboard` should be listed with the correct domain.

---

## Task 9: End-to-end smoke test

- [ ] **Step 1: Test mobile access (Cloudflare Access gate)**

Open `https://dashboard.<your-domain>` on your phone or in an incognito browser window.

Expected: Cloudflare Access login page appears. After Google login with `t8522192@gmail.com`, dashboard loads.

- [ ] **Step 2: Test the hook script change-detection path**

```bash
# Simulate a pipeline file change
touch /home/tim-huang/content-creation/src/pipeline/__init__.py
git -C /home/tim-huang/content-creation status --porcelain src/pipeline/
```

Expected: `M  src/pipeline/__init__.py` or similar (shows as modified).

```bash
# Run the hook script manually
/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh
sleep 3
systemctl --user status content-dashboard.service --no-pager | grep Active
```

Expected: `Active: active (running)` (service restarted and came back up).

```bash
# Restore the file
git -C /home/tim-huang/content-creation checkout src/pipeline/__init__.py
```

- [ ] **Step 3: Test the hook script no-change path**

```bash
git -C /home/tim-huang/content-creation status --porcelain src/pipeline/
```

Expected: empty output (clean working tree).

```bash
/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh
echo "exit: $?"
```

Expected: exit code 0, no restart triggered (verify with `journalctl --user -u content-dashboard.service -n 5 --no-pager` — no recent restart).

- [ ] **Step 4: Test reboot survival (optional but recommended)**

```bash
sudo reboot
```

After reboot, run:

```bash
systemctl --user status content-dashboard.service --no-pager
systemctl --user status cloudflared-named-tunnel.service --no-pager
curl -s http://localhost:8765/api/projects | head -c 50
```

Expected: both services `active (running)`, dashboard API responds.
