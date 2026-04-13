# Contributing

Thanks for considering a contribution to Hermes Control Plane.

## Scope for v0.1

Please keep contributions aligned with the current public scope:
- observer/dashboard for Hermes state
- cron visibility and cron actions
- host-native deployment with uv + systemd user service
- localhost-first security posture

Out of scope for v0.1:
- built-in auth inside FastAPI
- raw profile config viewer/editor
- large product roadmap work that is not implemented yet
- replacing the current lightweight server-rendered UI with a bigger frontend stack

## Development setup

```bash
uv sync
cp .env.example .env
uv run pytest -q
uv run uvicorn hermes_controlplane.main:app --host 127.0.0.1 --port 8780 --reload
```

## Guidelines

- keep changes small and focused
- preserve read-only access to Hermes SQLite state
- do not add direct writes to Hermes state databases
- keep cron actions routed through Hermes CLI behavior
- prefer simple host-native operations over new infrastructure
- sanitize docs, examples, and fixtures before opening PRs

## Tests

Please add or update tests when behavior changes.

At minimum, run:

```bash
uv run pytest -q
```

## Pull requests

A good PR usually includes:
- clear problem statement
- concise implementation notes
- tests or rationale when tests are not practical
- documentation updates when user-facing behavior changes

## Security issues

Please do not open public issues for sensitive security reports. Use the guidance in `SECURITY.md`.
