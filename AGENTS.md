# Hermes Control Plane — Agent Context

Open source sidecar/plugin for Hermes.

Current public scope:
- read-only observation of Hermes session state
- dashboard and JSON API
- cron visibility and cron actions
- host-native operation with uv + systemd user service
- localhost-first deployment

Run locally:

```bash
uv sync
uv run uvicorn hermes_controlplane.main:app --host 127.0.0.1 --port 8780
```

Run tests:

```bash
uv run pytest -q
```

Recommended remote access:

```bash
ssh -L 8780:127.0.0.1:8780 your-user@your-server
```

Notes:
- Docker is not the official deployment path for v0.1.
- Keep the app bound to localhost by default.
- Tailscale is an advanced option, not the baseline setup.
- Do not reintroduce raw profile config viewing/editing in v0.1.
- Keep the dashboard server-rendered and lightweight.
