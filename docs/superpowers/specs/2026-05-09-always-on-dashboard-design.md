# Always-On Dashboard: Named Tunnel + AI Agent Stop Hook

**Date:** 2026-05-09
**Status:** Approved

## Goal

Keep the content dashboard permanently accessible at a stable HTTPS URL (mobile-bookmarkable), auto-restart the server when AI agents finish a work session that touched pipeline code, and gate access behind Google OAuth.

## Architecture

```
[Claude Code STOP hook]     [Codex STOP hook]
          │                        │
          └────────┬───────────────┘
                   ▼
   scripts/restart-dashboard-if-changed.sh
     └─ git status --porcelain src/pipeline/
          ├─ changes found → systemctl --user restart content-dashboard
          └─ no changes   → exit 0 (no-op)

[systemd user services]
  content-dashboard.service          (FastAPI on localhost:8765, Restart=on-failure)
  cloudflared-named-tunnel.service   (Named Tunnel → dashboard.<domain>, Restart=always)

[Cloudflare]
  Named Tunnel → dashboard.<domain>
  Cloudflare Access policy → allow t8522192@gmail.com only
```

## Components

### 1. Restart-on-stop hook script

**Path:** `scripts/restart-dashboard-if-changed.sh`

Invoked by both Claude Code and Codex on their `Stop` event. Receives stdin JSON (ignored — no fields needed). Runs:

```bash
git status --porcelain src/pipeline/
```

If output is non-empty (any modified, added, deleted, or untracked file under `src/pipeline/`), restarts the dashboard service via `systemctl --user restart content-dashboard`. Always exits 0 so neither agent is blocked from stopping.

Scope is `src/pipeline/` broadly — changes to any pipeline module (not just `dashboard/`) can affect dashboard behavior.

### 2. Claude Code Stop hook

Configured in `~/.claude/settings.json` (global scope — applies to all projects on this machine):

```json
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
```

`matcher` is omitted — per docs, omitting it matches every Stop event regardless of project or context.

### 3. Codex Stop hook

Configured in Codex's `hooks.json` (location: `~/.codex/hooks.json` or the project's `codex.toml` `[hooks]` section):

```json
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
```

### 4. content-dashboard.service

Systemd user service. No `--reload` (server is stable for mobile use; restarts are controlled by the Stop hook).

```ini
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

[Install]
WantedBy=default.target
```

### 5. cloudflared-named-tunnel.service

Systemd user service using a pre-created Named Tunnel (not Quick Tunnel). Reconnects to the same stable URL on every restart.

```ini
[Unit]
Description=Cloudflare Named Tunnel (content dashboard)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/tim-huang/.local/bin/cloudflared tunnel run content-dashboard
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

The tunnel config lives at `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: /home/tim-huang/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: dashboard.<domain>
    service: http://localhost:8765
  - service: http_status:404
```

### 6. Cloudflare Access policy

Created in the Cloudflare dashboard (Zero Trust → Access → Applications):

- **Application:** `dashboard.<domain>`
- **Policy type:** Allow
- **Rule:** Email is `t8522192@gmail.com`

No dashboard code changes required. Cloudflare terminates TLS and enforces the Google OAuth challenge before any request reaches the tunnel.

## Behavior Matrix

| Scenario | Behavior |
|---|---|
| AI session with `src/pipeline/` changes | Stop hook → diff detects changes → `systemctl --user restart content-dashboard` |
| AI session with no code changes | Stop hook → diff empty → exits 0, no restart |
| Machine reboot | Both systemd services auto-start via `WantedBy=default.target` |
| Dashboard crash | `Restart=on-failure` brings it back within 5s |
| Tunnel disconnect | `Restart=always` reconnects; same Named Tunnel URL persists |
| Mobile access | `dashboard.<domain>` → Cloudflare Access → Google login → dashboard |
| Manual Python edit outside AI | `systemctl --user restart content-dashboard` (or `dashrs` shell alias) |
| Frontend (JS/HTML) edit | Browser refresh loads fresh assets via no-store headers and mtime `?v=` script URLs; no Cloudflare restart or cache clear needed |

## Security

- Dashboard binds to `localhost:8765` only — not reachable from the network directly
- All external traffic flows through Cloudflare's edge (TLS terminated there)
- Cloudflare Access blocks every request not authenticated as `t8522192@gmail.com`
- Named Tunnel credentials stored at `~/.cloudflared/` (mode 0600)

## One-Time Setup Steps (implementation order)

1. Create `scripts/restart-dashboard-if-changed.sh` and make executable
2. Merge Stop hook config into `~/.claude/settings.json` (preserve existing hooks)
3. Configure Codex Stop hook
4. Create `~/.config/systemd/user/content-dashboard.service`
5. Create `~/.config/systemd/user/cloudflared-named-tunnel.service`
6. Run `cloudflared login`, `cloudflared tunnel create content-dashboard`, add DNS CNAME
7. Write `~/.cloudflared/config.yml`
8. Enable and start both services (`systemctl --user enable --now`)
9. Create Cloudflare Access application in Zero Trust dashboard
10. Verify: mobile browser hits `dashboard.<domain>`, completes Google auth, sees dashboard

## Out of Scope

- Multi-user access (single-user design; no role-based policies)
- Dashboard authentication layer (Cloudflare Access handles this entirely)
- Hot-reload of Python code during active AI sessions (restarts happen at session end, not per-save)
- Notification when dashboard restarts (can be added later via Telegram notifier)
