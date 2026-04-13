# Hermes Control Plane — Agent Context

Read-only observation sidecar for [Hermes](https://github.com/matiasdaloia/hermes), an AI agent gateway.
Exposes a web dashboard and JSON API over the Hermes SQLite state — zero writes, zero impact on the host process.

---

## Stack

- **Backend**: Python 3.12, FastAPI, uvicorn (run directly on host — not Docker)
- **Frontend**: HTMX 2.0.4 + Jinja2 templates (no Node, no build step)
- **Charts**: Chart.js 4.4.7 via CDN
- **Markdown**: marked.js via CDN (cron output modal)
- **Database**: aiosqlite, opened with `?mode=ro` URI (read-only)
- **Fonts**: IBM Plex Sans + IBM Plex Mono via Google Fonts
- **Tests**: pytest

## Running

```bash
# Install dependencies
uv sync

# Start server
.venv/bin/uvicorn hermes_controlplane.main:app --host 127.0.0.1 --port 8780

# Run tests
.venv/bin/python -m pytest tests/ -q
```

Access from a local browser via SSH tunnel:
```bash
ssh -L 8780:127.0.0.1:8780 matias@<server-ip>
# then open http://localhost:8780
```

**Do not use Docker** — the container can't access host systemd (profile state shows as `unknown`) and WAL file locking causes zero sessions to appear.

---

## Architecture

Observer-only phase (Phase 1 of the PRD). No writes to Hermes state.

```
~/.hermes/
├── state.db                          # global sessions DB (WAL mode)
├── cron/
│   ├── jobs.json                     # global cron job definitions
│   └── output/{job_id}/{ts}.md       # cron run outputs
└── profiles/
    └── {name}/
        ├── state.db                  # per-profile sessions DB
        └── cron/
            ├── jobs.json
            └── output/{job_id}/{ts}.md
```

### Database schema (key tables)

**sessions**: id, source, model, billing_provider, started_at, ended_at, message_count,
tool_call_count, input_tokens, output_tokens, cache_read_tokens, reasoning_tokens,
estimated_cost_usd, cost_status, title

**messages**: id, session_id, role, content, created_at, ...

`cost_status = 'included'` means the session was billed via subscription (e.g. GPT-5.4 via
openai-codex) — cost shows as "incl." in the UI, not $0.00.

---

## Routing

Multi-page app. Each URL is a full page with its own data fetch.

| URL | Description |
|-----|-------------|
| `/` | Global overview — KPIs + charts |
| `/sessions` | Global sessions table with filters + pagination |
| `/cron` | Global cron jobs |
| `/profiles/{name}` | Profile overview — KPIs + charts scoped to profile DB |
| `/profiles/{name}/sessions` | Profile sessions |
| `/profiles/{name}/cron` | Profile cron jobs |

HTMX partials (used for live refresh inside pages):
- `GET /partials/kpi?range=&profile=` — KPI cards
- `GET /partials/charts?range=&profile=` — all charts
- `GET /partials/sessions?...` — session table rows
- `GET /partials/profiles` — profile table rows

---

## Template system

Single template: `hermes_controlplane/templates/dashboard.html`

Context variables passed to every page:

| Variable | Type | Description |
|----------|------|-------------|
| `page_section` | `str` | `'overview'` \| `'sessions'` \| `'cron'` |
| `page_title` | `str` | H1 text |
| `page_subtitle` | `str\|None` | Subtitle (mono, profile pages only) |
| `profile_name` | `str\|None` | Set on profile pages |
| `api_prefix` | `str` | `''` (global) or `/api/profiles/{name}` |
| `sidebar_profiles` | `list` | All profiles — always passed for sidebar nav |

Sections rendered conditionally via `{% if page_section == 'xxx' %}`.
JS blocks are also gated — `sessions.total` is only referenced inside the sessions block.

### Sidebar navigation

```
GENERAL
  Overview       /
  Sessions       /sessions
  Cron Jobs      /cron

PROFILES
  • radar        /profiles/radar
      Overview   /profiles/radar          ← shown only when radar is active
      Sessions   /profiles/radar/sessions
      Cron Jobs  /profiles/radar/cron
  • webhook      /profiles/webhook
      ...
```

Sidebar collapses to 52px. State persisted in `localStorage('sb-collapsed')`.
Sub-items under a profile are hidden when the sidebar is collapsed.

---

## Design system

CSS variables in `dashboard.html` `<style>` block:

```css
--bg:       #0c0d10   /* page background */
--surface:  #131419   /* card / sidebar background */
--border:   #1e2028   /* default border */
--text:     #dde1ec   /* primary text */
--text-2:   #9299b0   /* secondary / muted */
--text-3:   #464c62   /* dim / labels */
--accent:   #7fa8f5   /* primary accent (blue) */
--amber:    #fbbf24   /* cost indicators */
--green:    #34d399   /* active / success */
--red:      #f87171   /* error / inactive */
```

Charts use `requestAnimationFrame` for initialization to avoid blurry renders on HTMX swap.

---

## Key conventions

- **No builds**: never run `npm build`, `pip install` in response to a code change — just edit and reload
- **Read-only**: never add any write path to the observer; all DB access uses `?mode=ro`
- **Jinja2 dict access**: use `sessions["items"]` not `sessions.items` — dot notation resolves to Python's dict `.items()` method
- **Per-profile DB**: `_resolve_profile_db(name)` in `main.py` raises 404 if profile or its `state.db` doesn't exist
- **Sidebar profiles**: always fetch `get_all_profiles()` and pass as `sidebar_profiles` to every HTML route
- **`_base_ctx()`**: helper in `main.py` — use it for all page routes to avoid boilerplate
