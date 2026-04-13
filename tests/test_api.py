from fastapi.testclient import TestClient

from hermes_controlplane.main import app
from hermes_controlplane.observer import ProfileSummary


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
        }
    ]
    return {"items": items, "total": 1, "limit": 20, "offset": 0}


async def fake_overview(**kwargs):
    return {
        "total_sessions": 10, "total_messages": 100, "total_cost_usd": 5.0,
        "total_input_tokens": 50000, "total_output_tokens": 5000,
        "total_cache_read_tokens": 10000, "total_reasoning_tokens": 500,
        "active_sessions": 2, "distinct_models": 3, "distinct_sources": 2,
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
    assert response.json()["status"] == "ok"


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
