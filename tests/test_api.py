from fastapi.testclient import TestClient

from hermes_controlplane.main import app
from hermes_controlplane.observer import ProfileSummary
from hermes_controlplane import cron_actions


client = TestClient(app)


async def fake_profiles():
    return [
        ProfileSummary(
            name="radar",
            systemd_state="active",
            model="gpt-5.4",
            provider="openai-codex",
            session_count=3,
        ).to_dict()
    ]


async def fake_profile(name: str):
    if name == "radar":
        return ProfileSummary(name="radar", systemd_state="active")
    return ProfileSummary(name=name, exists=False)


async def fake_sessions(**kwargs):
    items = [
        {
            "id": "sess-1",
            "source": "telegram",
            "model": "gpt-5.4",
            "started_at": "2026-04-12T12:00:00+00:00",
            "ended_at": None,
            "message_count": 4,
            "tool_call_count": 2,
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_tokens": 200,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_status": "estimated",
            "title": None,
            "duration_seconds": None,
            "was_auto_reset": False,
            "auto_reset_reason": None,
            "cache_write_tokens": 0,
        }
    ]
    return {"items": items, "total": 1, "limit": 20, "offset": 0}


async def fake_overview(**kwargs):
    return {
        "total_sessions": 10, "total_messages": 100, "total_cost_usd": 5.0,
        "total_input_tokens": 50000, "total_output_tokens": 5000,
        "total_cache_read_tokens": 10000, "total_reasoning_tokens": 500,
        "active_sessions": 2, "distinct_models": 3, "distinct_sources": 2,
        "total_tool_calls": 42, "avg_duration_seconds": 300.0,
        "total_cache_write_tokens": 2000, "cache_efficiency_ratio": 0.167,
    }


async def fake_costs_by_model(**kwargs):
    return [{"model": "gpt-5.4", "sessions": 5, "cost_usd": 3.0, "input_tokens": 30000, "output_tokens": 3000, "messages": 50}]


async def fake_sources(**kwargs):
    return [{"source": "telegram", "sessions": 5, "messages": 50, "cost_usd": 3.0}]


async def fake_hourly(**kwargs):
    return [{"hour": h, "messages": 10 if h == 21 else 0} for h in range(24)]


async def fake_daily(**kwargs):
    return [{"date": "2026-04-12", "sessions": 5, "messages": 100, "cost_usd": 3.0}]


async def fake_filter_options(**kwargs):
    return {"sources": ["telegram", "cli"], "models": ["gpt-5.4"]}


async def fake_profile_names():
    return ["radar"]


async def fake_session_detail_found(session_id, **kwargs):
    if session_id == "sess-1":
        return {
            "id": "sess-1",
            "source": "cli",
            "model": "gpt-5.4",
            "started_at": "2026-04-12T12:00:00+00:00",
            "ended_at": "2026-04-12T12:30:00+00:00",
            "message_count": 4,
            "tool_call_count": 2,
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_tokens": 200,
            "reasoning_tokens": 50,
            "estimated_cost_usd": 0.05,
            "cost_status": "estimated",
            "title": "Test session",
            "cache_write_tokens": 80,
            "was_auto_reset": False,
            "auto_reset_reason": None,
            "duration_seconds": 1800,
        }
    return None


async def fake_session_detail_none(session_id, **kwargs):
    return None


async def fake_session_messages(session_id, **kwargs):
    return [
        {"id": "msg-1", "role": "user", "content": "Hello", "created_at": "2026-04-12T12:00:01+00:00"},
        {"id": "msg-2", "role": "assistant", "content": "Hi there", "created_at": "2026-04-12T12:00:02+00:00"},
    ]


def _patch_overview(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_overview_stats", fake_overview)
    monkeypatch.setattr("hermes_controlplane.main.get_costs_by_model", fake_costs_by_model)
    monkeypatch.setattr("hermes_controlplane.main.get_sessions_by_source", fake_sources)
    monkeypatch.setattr("hermes_controlplane.main.get_hourly_activity", fake_hourly)
    monkeypatch.setattr("hermes_controlplane.main.get_daily_stats", fake_daily)


def _patch_sessions(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions)
    monkeypatch.setattr("hermes_controlplane.main.get_filter_options", fake_filter_options)


def _patch_cron(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_cron_jobs", lambda **kw: [])
    monkeypatch.setattr("hermes_controlplane.main.get_all_cron_output_jobs", lambda **kw: [])


def test_health(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.list_profiles", fake_profile_names)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "ok",
        "version": "0.1.0",
        "mode": "observer-first",
        "profiles_found": 1,
    }
    assert "hermes_home" not in data
    assert "profiles" not in data


def test_profile_raw_config_route_removed():
    response = client.get("/profiles/radar/config")
    assert response.status_code == 404


def test_api_profiles(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    response = client.get("/api/profiles")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "radar"


def test_api_profile_found(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_profile_summary", fake_profile)
    response = client.get("/api/profiles/radar")
    assert response.status_code == 200
    assert response.json()["name"] == "radar"


def test_api_profile_not_found(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_profile_summary", fake_profile)
    response = client.get("/api/profiles/missing")
    assert response.status_code == 404


def test_recent_sessions(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions)
    response = client.get("/api/sessions/recent?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["id"] == "sess-1"
    assert data["total"] == 1


def test_overview_stats(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_overview_stats", fake_overview)
    response = client.get("/api/stats/overview")
    assert response.status_code == 200
    assert response.json()["total_sessions"] == 10


def test_page_overview_renders(monkeypatch):
    _patch_overview(monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "Overview" in response.text
    assert "radar" in response.text


def test_page_sessions_renders(monkeypatch):
    _patch_sessions(monkeypatch)
    response = client.get("/sessions")
    assert response.status_code == 200
    assert "Sessions" in response.text


def test_page_cron_renders(monkeypatch):
    _patch_cron(monkeypatch)
    response = client.get("/cron")
    assert response.status_code == 200
    assert "Cron" in response.text


# ---------------------------------------------------------------------------
# 4.6 — GET /sessions/{id}
# ---------------------------------------------------------------------------

def test_session_detail_200_for_valid_session(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_session_detail", fake_session_detail_found)
    monkeypatch.setattr("hermes_controlplane.main.get_session_messages", fake_session_messages)
    response = client.get("/sessions/sess-1")
    assert response.status_code == 200
    assert "sess-1" in response.text
    assert "Test session" in response.text


def test_session_detail_404_for_unknown(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_session_detail", fake_session_detail_none)
    monkeypatch.setattr("hermes_controlplane.main.get_session_messages", fake_session_messages)
    response = client.get("/sessions/no-such-session")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4.7 — GET /profiles/{name}/sessions/{id}
# ---------------------------------------------------------------------------

def test_profile_session_detail_200_for_valid_pair(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_profile_summary", fake_profile)
    monkeypatch.setattr("hermes_controlplane.main.get_session_detail", fake_session_detail_found)
    monkeypatch.setattr("hermes_controlplane.main.get_session_messages", fake_session_messages)
    response = client.get("/profiles/radar/sessions/sess-1")
    assert response.status_code == 200
    assert "sess-1" in response.text


def test_profile_session_detail_404_for_unknown_session(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_all_profiles", fake_profiles)
    monkeypatch.setattr("hermes_controlplane.main.get_profile_summary", fake_profile)
    monkeypatch.setattr("hermes_controlplane.main.get_session_detail", fake_session_detail_none)
    monkeypatch.setattr("hermes_controlplane.main.get_session_messages", fake_session_messages)
    response = client.get("/profiles/radar/sessions/no-such")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4.8 — KPI partial includes new fields
# ---------------------------------------------------------------------------

def test_kpi_partial_includes_tool_calls(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_overview_stats", fake_overview)
    response = client.get("/partials/kpi")
    assert response.status_code == 200
    # overview has total_tool_calls=42 — should appear in KPI card
    assert "42" in response.text


def test_kpi_partial_includes_cache_efficiency(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_overview_stats", fake_overview)
    response = client.get("/partials/kpi")
    assert response.status_code == 200
    # cache_efficiency_ratio = 0.167 → ~16.7% — "16" should appear
    assert "16" in response.text


# ---------------------------------------------------------------------------
# 4.10 — Sessions partial: Running badge, platform badge, cost prefix
# ---------------------------------------------------------------------------

async def fake_sessions_running(**kwargs):
    items = [
        {
            "id": "sess-run",
            "source": "telegram",
            "model": "gpt-5.4",
            "started_at": "2026-04-12T12:00:00+00:00",
            "ended_at": None,
            "message_count": 2,
            "tool_call_count": 0,
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_status": None,
            "title": None,
            "duration_seconds": None,
            "was_auto_reset": False,
            "auto_reset_reason": None,
            "cache_write_tokens": 0,
        }
    ]
    return {"items": items, "total": 1, "limit": 20, "offset": 0}


async def fake_sessions_with_costs(**kwargs):
    items = [
        {
            "id": "sess-incl",
            "source": "cli",
            "model": "gpt-5.4",
            "started_at": "2026-04-12T12:00:00+00:00",
            "ended_at": "2026-04-12T12:30:00+00:00",
            "message_count": 3,
            "tool_call_count": 1,
            "input_tokens": 500,
            "output_tokens": 200,
            "cache_read_tokens": 50,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.05,
            "cost_status": "included",
            "title": None,
            "duration_seconds": 1800,
            "was_auto_reset": False,
            "auto_reset_reason": None,
            "cache_write_tokens": 0,
        },
        {
            "id": "sess-approx",
            "source": "webhook",
            "model": "gpt-5.4",
            "started_at": "2026-04-12T11:00:00+00:00",
            "ended_at": "2026-04-12T11:10:00+00:00",
            "message_count": 2,
            "tool_call_count": 0,
            "input_tokens": 300,
            "output_tokens": 100,
            "cache_read_tokens": 30,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.03,
            "cost_status": "estimated",
            "title": None,
            "duration_seconds": 600,
            "was_auto_reset": True,
            "auto_reset_reason": "idle",
            "cache_write_tokens": 0,
        },
    ]
    return {"items": items, "total": 2, "limit": 20, "offset": 0}


def test_sessions_partial_running_badge(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions_running)
    response = client.get("/partials/sessions")
    assert response.status_code == 200
    assert "Running" in response.text


def test_sessions_partial_platform_badge_present(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions_running)
    response = client.get("/partials/sessions")
    assert response.status_code == 200
    # telegram badge should appear
    assert "telegram" in response.text


def test_sessions_partial_cost_included_prefix(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions_with_costs)
    response = client.get("/partials/sessions")
    assert response.status_code == 200
    assert "incl." in response.text


def test_sessions_partial_cost_estimated_prefix(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions_with_costs)
    response = client.get("/partials/sessions")
    assert response.status_code == 200
    assert "~$" in response.text


def test_sessions_partial_auto_reset_badge(monkeypatch):
    monkeypatch.setattr("hermes_controlplane.main.get_recent_sessions", fake_sessions_with_costs)
    response = client.get("/partials/sessions")
    assert response.status_code == 200
    assert "idle" in response.text


# ===========================================================================
# Cron partial and action routes
# ===========================================================================

# Fake cron job data helpers

def _fake_job(job_id: str = "job-1", state: str = "scheduled") -> dict:
    return {
        "id": job_id,
        "name": "Test Job",
        "schedule_display": "every 1h",
        "state": state,
        "enabled": True,
        "deliver": None,
        "model": None,
        "provider": None,
        "script": None,
        "repeat_times": None,
        "repeat_completed": 0,
        "next_run_at": None,
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "created_at": None,
        "output_count": 0,
        "prompt_preview": "Do something",
        "run_history": [],
        "last_delivery_error": None,
        "paused_reason": None,
    }


async def fake_run_job_ok(job_id, hermes_home=None):
    return {"success": True, "output": "ok", "error": None}


async def fake_pause_job_ok(job_id, hermes_home=None):
    return {"success": True, "output": "ok", "error": None}


async def fake_resume_job_ok(job_id, hermes_home=None):
    return {"success": True, "output": "ok", "error": None}


def _patch_cron_jobs(monkeypatch, jobs):
    monkeypatch.setattr("hermes_controlplane.main.get_cron_jobs", lambda **kw: jobs)
    monkeypatch.setattr("hermes_controlplane.main.get_all_cron_output_jobs", lambda **kw: [])


# ---------------------------------------------------------------------------
# 5.9 — GET /partials/cron returns HTML with cron table content
# ---------------------------------------------------------------------------

def test_partial_cron_get_returns_html(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "scheduled")])
    response = client.get("/partials/cron")
    assert response.status_code == 200
    assert "job-1" in response.text
    assert "Test Job" in response.text
    assert "cron-section" in response.text


def test_partial_cron_get_no_jobs_renders_empty(monkeypatch):
    _patch_cron_jobs(monkeypatch, [])
    response = client.get("/partials/cron")
    assert response.status_code == 200
    assert "cron-section" in response.text


# ---------------------------------------------------------------------------
# 5.5 — POST .../run happy path → 200 HTML containing job id
# ---------------------------------------------------------------------------

def test_partial_cron_run_happy_path(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "scheduled")])
    monkeypatch.setattr(cron_actions, "run_job", fake_run_job_ok)
    response = client.post("/partials/cron/jobs/job-1/run")
    assert response.status_code == 200
    assert "cron-section" in response.text


# ---------------------------------------------------------------------------
# 5.6 — POST .../run with state=running → 409
# ---------------------------------------------------------------------------

def test_partial_cron_run_already_running_returns_409(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "running")])
    response = client.post("/partials/cron/jobs/job-1/run")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# 5.7 — POST .../pause happy path and already-paused → 409
# ---------------------------------------------------------------------------

def test_partial_cron_pause_happy_path(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "scheduled")])
    monkeypatch.setattr(cron_actions, "pause_job", fake_pause_job_ok)
    response = client.post("/partials/cron/jobs/job-1/pause")
    assert response.status_code == 200
    assert "cron-section" in response.text


def test_partial_cron_pause_already_paused_returns_409(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "paused")])
    response = client.post("/partials/cron/jobs/job-1/pause")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# 5.8 — POST .../resume happy path
# ---------------------------------------------------------------------------

def test_partial_cron_resume_happy_path(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "paused")])
    monkeypatch.setattr(cron_actions, "resume_job", fake_resume_job_ok)
    response = client.post("/partials/cron/jobs/job-1/resume")
    assert response.status_code == 200
    assert "cron-section" in response.text


def test_partial_cron_resume_not_paused_returns_409(monkeypatch):
    _patch_cron_jobs(monkeypatch, [_fake_job("job-1", "scheduled")])
    response = client.post("/partials/cron/jobs/job-1/resume")
    assert response.status_code == 409
