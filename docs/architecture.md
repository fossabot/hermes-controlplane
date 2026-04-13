# Architecture

## Overview

Hermes Control Plane is a lightweight sidecar/plugin for Hermes.

v0.1 has two functional areas:
- observation of Hermes state and profiles
- cron visibility plus cron actions

## Main components

### FastAPI app

`hermes_controlplane.main`
- exposes HTML routes for the dashboard
- exposes JSON endpoints for sessions, stats, profiles, and cron data
- exposes HTMX partial routes used by the dashboard

### Observer

`hermes_controlplane.observer`
- reads Hermes SQLite state using `mode=ro`
- aggregates overview metrics
- lists sessions and messages
- resolves profile summaries from Hermes profiles

### Cron observer

`hermes_controlplane.cron_observer`
- reads Hermes cron job definitions
- reads cron output files
- provides profile-scoped and global cron views

### Cron actions

`hermes_controlplane.cron_actions`
- executes cron run/pause/resume operations through the Hermes CLI
- does not mutate Hermes state databases directly

## Data model assumptions

The app expects a Hermes home like:

```text
~/.hermes/
├── state.db
├── cron/
│   ├── jobs.json
│   └── output/
└── profiles/
    └── <name>/
        ├── state.db
        └── cron/
```

## Security posture

- session/state reads are read-only
- official deployment binds to localhost
- remote access is expected through SSH tunnel
- Tailscale is documented as an advanced option
- there is no in-app auth layer in v0.1

## UI model

The dashboard is server-rendered with Jinja2 and progressively refreshed with HTMX.

This keeps the project simple:
- no Node toolchain
- no frontend build step
- minimal operational overhead
