"""Hermes Control Plane — FastAPI sidecar for Hermes observability and cron operations."""

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from hermes_controlplane.config import settings
from hermes_controlplane import cron_actions
from hermes_controlplane.cron_observer import (
    get_all_cron_output_jobs,
    get_cron_jobs,
    get_cron_output_content,
    get_cron_outputs,
)
from hermes_controlplane.observer import (
    get_all_profiles,
    get_costs_by_model,
    get_daily_stats,
    get_filter_options,
    get_hourly_activity,
    get_overview_stats,
    get_profile_summary,
    get_recent_sessions,
    get_session_detail,
    get_session_messages,
    get_sessions_by_source,
    list_profiles,
)

app = FastAPI(
    title="Hermes Control Plane",
    version="0.1.0",
    description="Hermes observability sidecar with cron operations for Hermes",
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

RANGE_PRESETS = {"24h": 86400, "7d": 604800, "30d": 2592000}


def _parse_time_range(
    range_preset: str | None, since: float | None, until: float | None,
) -> tuple[float | None, float | None]:
    if range_preset and range_preset in RANGE_PRESETS:
        return time.time() - RANGE_PRESETS[range_preset], until
    return since, until


def _resolve_profile_db(name: str) -> Path:
    """Resolve profile state.db path, raise 404 if profile doesn't exist."""
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    db = profile_dir / "state.db"
    if not db.exists():
        raise HTTPException(status_code=404, detail=f"No state.db for profile '{name}'")
    return db


# =========================================================================
# JSON API — Global
# =========================================================================

@app.get("/health")
async def health():
    profiles = await list_profiles()
    return {
        "status": "ok",
        "version": app.version,
        "mode": "observer-first",
        "profiles_found": len(profiles),
    }


@app.get("/api/profiles")
async def api_profiles():
    return await get_all_profiles()


@app.get("/api/profiles/{name}")
async def api_profile(name: str):
    summary = await get_profile_summary(name)
    if not summary.exists:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return summary.to_dict()


@app.get("/api/sessions/recent")
async def api_recent_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    model: str | None = Query(default=None),
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    return await get_recent_sessions(
        limit=limit, offset=offset, source=source, model=model, since=s, until=u,
    )


@app.get("/api/sessions/filters")
async def api_session_filters():
    return await get_filter_options()


@app.get("/api/stats/overview")
async def api_overview_stats(
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    return await get_overview_stats(since=s, until=u)


@app.get("/api/stats/costs-by-model")
async def api_costs_by_model(
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    return await get_costs_by_model(since=s, until=u)


@app.get("/api/stats/sessions-by-source")
async def api_sessions_by_source(
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    return await get_sessions_by_source(since=s, until=u)


@app.get("/api/stats/hourly-activity")
async def api_hourly_activity(
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    return await get_hourly_activity(since=s, until=u)


@app.get("/api/stats/daily")
async def api_daily_stats(
    days: int = Query(default=7, ge=1, le=90),
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    return await get_daily_stats(days=days, since=s, until=u)


# =========================================================================
# JSON API — Per-profile (scoped to profile's state.db)
# =========================================================================

@app.get("/api/profiles/{name}/sessions/recent")
async def api_profile_sessions(
    name: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    model: str | None = Query(default=None),
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    db = _resolve_profile_db(name)
    s, u = _parse_time_range(range, since, until)
    return await get_recent_sessions(
        limit=limit, offset=offset, source=source, model=model, since=s, until=u, db_path=db,
    )


@app.get("/api/profiles/{name}/sessions/filters")
async def api_profile_session_filters(name: str):
    db = _resolve_profile_db(name)
    return await get_filter_options(db_path=db)


@app.get("/api/profiles/{name}/stats/overview")
async def api_profile_overview(
    name: str,
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    db = _resolve_profile_db(name)
    s, u = _parse_time_range(range, since, until)
    return await get_overview_stats(since=s, until=u, db_path=db)


@app.get("/api/profiles/{name}/stats/costs-by-model")
async def api_profile_costs(
    name: str,
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    db = _resolve_profile_db(name)
    s, u = _parse_time_range(range, since, until)
    return await get_costs_by_model(since=s, until=u, db_path=db)


@app.get("/api/profiles/{name}/stats/sessions-by-source")
async def api_profile_sources(
    name: str,
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    db = _resolve_profile_db(name)
    s, u = _parse_time_range(range, since, until)
    return await get_sessions_by_source(since=s, until=u, db_path=db)


@app.get("/api/profiles/{name}/stats/hourly-activity")
async def api_profile_hourly(
    name: str,
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    db = _resolve_profile_db(name)
    s, u = _parse_time_range(range, since, until)
    return await get_hourly_activity(since=s, until=u, db_path=db)


@app.get("/api/profiles/{name}/stats/daily")
async def api_profile_daily(
    name: str,
    days: int = Query(default=7, ge=1, le=90),
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
):
    db = _resolve_profile_db(name)
    s, u = _parse_time_range(range, since, until)
    return await get_daily_stats(days=days, since=s, until=u, db_path=db)


# =========================================================================
# JSON API — Cron
# =========================================================================

@app.get("/api/cron/jobs")
async def api_cron_jobs():
    return get_cron_jobs()


@app.get("/api/cron/jobs/{job_id}/outputs")
async def api_cron_outputs(job_id: str):
    return get_cron_outputs(job_id)


@app.get("/api/cron/jobs/{job_id}/outputs/{filename}")
async def api_cron_output_content(job_id: str, filename: str):
    content = get_cron_output_content(job_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Output not found")
    return {"content": content}


@app.get("/api/cron/output-jobs")
async def api_cron_output_jobs():
    return get_all_cron_output_jobs()


@app.get("/api/profiles/{name}/cron/jobs")
async def api_profile_cron_jobs(name: str):
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return get_cron_jobs(hermes_home=profile_dir)


@app.get("/api/profiles/{name}/cron/jobs/{job_id}/outputs")
async def api_profile_cron_outputs(name: str, job_id: str):
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return get_cron_outputs(job_id, hermes_home=profile_dir)


@app.get("/api/profiles/{name}/cron/jobs/{job_id}/outputs/{filename}")
async def api_profile_cron_output_content(name: str, job_id: str, filename: str):
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    content = get_cron_output_content(job_id, filename, hermes_home=profile_dir)
    if content is None:
        raise HTTPException(status_code=404, detail="Output not found")
    return {"content": content}


@app.get("/api/profiles/{name}/cron/output-jobs")
async def api_profile_cron_output_jobs(name: str):
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return get_all_cron_output_jobs(hermes_home=profile_dir)


# =========================================================================
# HTML pages
# =========================================================================

def _base_ctx(sidebar_profiles, page_title, page_section, profile_name=None,
              api_prefix="", page_subtitle=None, profiles=None):
    return {
        "sidebar_profiles": sidebar_profiles,
        "profiles": profiles or [],
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "page_section": page_section,
        "profile_name": profile_name,
        "api_prefix": api_prefix,
    }


@app.get("/", response_class=HTMLResponse)
async def page_overview(request: Request):
    sidebar_profiles = await get_all_profiles()
    overview = await get_overview_stats()
    costs_by_model = await get_costs_by_model()
    sources = await get_sessions_by_source()
    hourly = await get_hourly_activity()
    daily = await get_daily_stats()
    ctx = _base_ctx(sidebar_profiles, "Overview", "overview")
    ctx.update(overview=overview, costs_by_model=costs_by_model,
               sources=sources, hourly=hourly, daily=daily)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/sessions", response_class=HTMLResponse)
async def page_sessions(request: Request):
    sidebar_profiles = await get_all_profiles()
    sessions = await get_recent_sessions(limit=20)
    filters = await get_filter_options()
    ctx = _base_ctx(sidebar_profiles, "Sessions", "sessions")
    ctx.update(sessions=sessions, filters=filters)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/cron", response_class=HTMLResponse)
async def page_cron(request: Request):
    sidebar_profiles = await get_all_profiles()
    cron_jobs = get_cron_jobs()
    cron_output_jobs = get_all_cron_output_jobs()
    ctx = _base_ctx(sidebar_profiles, "Cron Jobs", "cron")
    ctx.update(cron_jobs=cron_jobs, cron_output_jobs=cron_output_jobs)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/profiles/{name}", response_class=HTMLResponse)
async def page_profile_overview(request: Request, name: str):
    db = _resolve_profile_db(name)
    summary = await get_profile_summary(name)
    sidebar_profiles = await get_all_profiles()
    overview = await get_overview_stats(db_path=db)
    costs_by_model = await get_costs_by_model(db_path=db)
    sources = await get_sessions_by_source(db_path=db)
    hourly = await get_hourly_activity(db_path=db)
    daily = await get_daily_stats(db_path=db)
    ctx = _base_ctx(sidebar_profiles, name, "overview", profile_name=name,
                    api_prefix=f"/api/profiles/{name}",
                    page_subtitle=f"{summary.model or 'unknown model'} via {summary.provider or 'unknown'}",
                    profiles=[summary.to_dict()])
    ctx.update(overview=overview, costs_by_model=costs_by_model,
               sources=sources, hourly=hourly, daily=daily)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/profiles/{name}/sessions", response_class=HTMLResponse)
async def page_profile_sessions(request: Request, name: str):
    db = _resolve_profile_db(name)
    summary = await get_profile_summary(name)
    sidebar_profiles = await get_all_profiles()
    sessions = await get_recent_sessions(limit=20, db_path=db)
    filters = await get_filter_options(db_path=db)
    ctx = _base_ctx(sidebar_profiles, name, "sessions", profile_name=name,
                    api_prefix=f"/api/profiles/{name}",
                    page_subtitle=f"{summary.model or 'unknown model'} via {summary.provider or 'unknown'}",
                    profiles=[summary.to_dict()])
    ctx.update(sessions=sessions, filters=filters)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/profiles/{name}/cron", response_class=HTMLResponse)
async def page_profile_cron(request: Request, name: str):
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    summary = await get_profile_summary(name)
    sidebar_profiles = await get_all_profiles()
    cron_jobs = get_cron_jobs(hermes_home=profile_dir)
    cron_output_jobs = get_all_cron_output_jobs(hermes_home=profile_dir)
    ctx = _base_ctx(sidebar_profiles, name, "cron", profile_name=name,
                    api_prefix=f"/api/profiles/{name}",
                    page_subtitle=f"{summary.model or 'unknown model'} via {summary.provider or 'unknown'}",
                    profiles=[summary.to_dict()])
    ctx.update(cron_jobs=cron_jobs, cron_output_jobs=cron_output_jobs)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
async def page_session_detail(request: Request, session_id: str):
    sidebar_profiles = await get_all_profiles()
    session = await get_session_detail(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    messages = await get_session_messages(session_id, limit=200)
    ctx = _base_ctx(sidebar_profiles, f"Session {session_id[:12]}…", "session_detail")
    ctx.update(session=session, messages=messages)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/profiles/{name}/sessions/{session_id}", response_class=HTMLResponse)
async def page_profile_session_detail(request: Request, name: str, session_id: str):
    db = _resolve_profile_db(name)
    sidebar_profiles = await get_all_profiles()
    summary = await get_profile_summary(name)
    session = await get_session_detail(session_id, db_path=db)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    messages = await get_session_messages(session_id, limit=200, db_path=db)
    ctx = _base_ctx(sidebar_profiles, f"Session {session_id[:12]}…", "session_detail",
                    profile_name=name,
                    api_prefix=f"/api/profiles/{name}",
                    page_subtitle=f"{summary.model or 'unknown model'} via {summary.provider or 'unknown'}",
                    profiles=[summary.to_dict()])
    ctx.update(session=session, messages=messages)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/cron/outputs/{job_id}/{filename}", response_class=HTMLResponse)
async def page_cron_output(request: Request, job_id: str, filename: str):
    sidebar_profiles = await get_all_profiles()
    content = get_cron_output_content(job_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Output not found")
    ctx = _base_ctx(sidebar_profiles, filename, "cron_output")
    ctx.update(cron_output_content=content, cron_output_job_id=job_id, cron_output_filename=filename)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/profiles/{name}/cron/outputs/{job_id}/{filename}", response_class=HTMLResponse)
async def page_profile_cron_output(request: Request, name: str, job_id: str, filename: str):
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    summary = await get_profile_summary(name)
    sidebar_profiles = await get_all_profiles()
    content = get_cron_output_content(job_id, filename, hermes_home=profile_dir)
    if content is None:
        raise HTTPException(status_code=404, detail="Output not found")
    ctx = _base_ctx(sidebar_profiles, filename, "cron_output",
                    profile_name=name,
                    api_prefix=f"/api/profiles/{name}",
                    page_subtitle=f"{summary.model or 'unknown model'} via {summary.provider or 'unknown'}",
                    profiles=[summary.to_dict()])
    ctx.update(cron_output_content=content, cron_output_job_id=job_id, cron_output_filename=filename)
    return templates.TemplateResponse(request=request, name="dashboard.html", context=ctx)


# =========================================================================
# HTMX partials — global & per-profile (api_prefix routes to correct DB)
# =========================================================================

@app.get("/api/sessions/{session_id}", response_class=HTMLResponse)
async def partial_session_detail(request: Request, session_id: str):
    session = await get_session_detail(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    messages = await get_session_messages(session_id, limit=200)
    return templates.TemplateResponse(
        request=request, name="partials/session_detail.html",
        context={"session": session, "messages": messages},
    )


@app.get("/api/profiles/{name}/sessions/{session_id}", response_class=HTMLResponse)
async def partial_profile_session_detail(request: Request, name: str, session_id: str):
    db = _resolve_profile_db(name)
    session = await get_session_detail(session_id, db_path=db)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    messages = await get_session_messages(session_id, limit=200, db_path=db)
    return templates.TemplateResponse(
        request=request, name="partials/session_detail.html",
        context={"session": session, "messages": messages},
    )


@app.get("/partials/kpi", response_class=HTMLResponse)
async def partial_kpi(
    request: Request,
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
    profile: str | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    db = _resolve_profile_db(profile) if profile else None
    overview = await get_overview_stats(since=s, until=u, db_path=db)
    return templates.TemplateResponse(
        request=request, name="partials/kpi.html", context={"overview": overview}
    )


@app.get("/partials/profiles", response_class=HTMLResponse)
async def partial_profiles(request: Request):
    profiles = await get_all_profiles()
    return templates.TemplateResponse(
        request=request, name="partials/profiles.html", context={"profiles": profiles}
    )


@app.get("/partials/sessions", response_class=HTMLResponse)
async def partial_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    model: str | None = Query(default=None),
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
    profile: str | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    db = _resolve_profile_db(profile) if profile else None
    sessions = await get_recent_sessions(
        limit=limit, offset=offset, source=source, model=model, since=s, until=u, db_path=db,
    )
    return templates.TemplateResponse(
        request=request, name="partials/sessions.html",
        context={"sessions": sessions, "profile_name": profile},
    )


@app.get("/partials/charts", response_class=HTMLResponse)
async def partial_charts(
    request: Request,
    range: str | None = Query(default=None, alias="range"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
    profile: str | None = Query(default=None),
):
    s, u = _parse_time_range(range, since, until)
    db = _resolve_profile_db(profile) if profile else None
    costs_by_model = await get_costs_by_model(since=s, until=u, db_path=db)
    sources = await get_sessions_by_source(since=s, until=u, db_path=db)
    hourly = await get_hourly_activity(since=s, until=u, db_path=db)
    daily = await get_daily_stats(since=s, until=u, db_path=db)
    return templates.TemplateResponse(
        request=request, name="partials/charts.html",
        context={
            "costs_by_model": costs_by_model,
            "sources": sources,
            "hourly": hourly,
            "daily": daily,
        },
    )


# =========================================================================
# HTMX partials — Cron (GET refresh + POST actions)
# =========================================================================

def _cron_partial_ctx(
    cron_jobs: list,
    cron_output_jobs: list,
    profile_name: str | None = None,
    action_error: str | None = None,
) -> dict:
    """Build context dict for the cron partial template."""
    return {
        "cron_jobs": cron_jobs,
        "cron_output_jobs": cron_output_jobs,
        "profile_name": profile_name,
        "action_error": action_error,
    }


@app.get("/partials/cron", response_class=HTMLResponse)
async def partial_cron(
    request: Request,
    profile: str | None = Query(default=None),
):
    if profile:
        hermes_home = settings.profiles_dir / profile
        if not hermes_home.is_dir():
            raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    else:
        hermes_home = None  # uses settings.hermes_home inside get_cron_jobs

    cron_jobs = get_cron_jobs(hermes_home=hermes_home)
    cron_output_jobs = get_all_cron_output_jobs(hermes_home=hermes_home)
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, profile_name=profile),
    )


# ── Global cron action routes ──────────────────────────────────────────────

@app.post("/partials/cron/jobs/{job_id}/run", response_class=HTMLResponse)
async def partial_cron_run(request: Request, job_id: str):
    jobs = get_cron_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job and job.get("state") == "running":
        raise HTTPException(status_code=409, detail="Job is already running")
    result = await cron_actions.run_job(job_id, hermes_home=settings.hermes_home)
    error = result["error"] if not result["success"] else None
    cron_jobs = get_cron_jobs()
    cron_output_jobs = get_all_cron_output_jobs()
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, action_error=error),
    )


@app.post("/partials/cron/jobs/{job_id}/pause", response_class=HTMLResponse)
async def partial_cron_pause(request: Request, job_id: str):
    jobs = get_cron_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job and job.get("state") == "paused":
        raise HTTPException(status_code=409, detail="Job is already paused")
    result = await cron_actions.pause_job(job_id, hermes_home=settings.hermes_home)
    error = result["error"] if not result["success"] else None
    cron_jobs = get_cron_jobs()
    cron_output_jobs = get_all_cron_output_jobs()
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, action_error=error),
    )


@app.post("/partials/cron/jobs/{job_id}/resume", response_class=HTMLResponse)
async def partial_cron_resume(request: Request, job_id: str):
    jobs = get_cron_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job and job.get("state") != "paused":
        raise HTTPException(status_code=409, detail="Job is not paused")
    result = await cron_actions.resume_job(job_id, hermes_home=settings.hermes_home)
    error = result["error"] if not result["success"] else None
    cron_jobs = get_cron_jobs()
    cron_output_jobs = get_all_cron_output_jobs()
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, action_error=error),
    )


# ── Profile-scoped cron action routes ─────────────────────────────────────

@app.post("/partials/cron/profiles/{name}/jobs/{job_id}/run", response_class=HTMLResponse)
async def partial_profile_cron_run(request: Request, name: str, job_id: str):
    hermes_home = settings.profiles_dir / name
    if not hermes_home.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    jobs = get_cron_jobs(hermes_home=hermes_home)
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job and job.get("state") == "running":
        raise HTTPException(status_code=409, detail="Job is already running")
    result = await cron_actions.run_job(job_id, hermes_home=hermes_home)
    error = result["error"] if not result["success"] else None
    cron_jobs = get_cron_jobs(hermes_home=hermes_home)
    cron_output_jobs = get_all_cron_output_jobs(hermes_home=hermes_home)
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, profile_name=name, action_error=error),
    )


@app.post("/partials/cron/profiles/{name}/jobs/{job_id}/pause", response_class=HTMLResponse)
async def partial_profile_cron_pause(request: Request, name: str, job_id: str):
    hermes_home = settings.profiles_dir / name
    if not hermes_home.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    jobs = get_cron_jobs(hermes_home=hermes_home)
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job and job.get("state") == "paused":
        raise HTTPException(status_code=409, detail="Job is already paused")
    result = await cron_actions.pause_job(job_id, hermes_home=hermes_home)
    error = result["error"] if not result["success"] else None
    cron_jobs = get_cron_jobs(hermes_home=hermes_home)
    cron_output_jobs = get_all_cron_output_jobs(hermes_home=hermes_home)
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, profile_name=name, action_error=error),
    )


@app.post("/partials/cron/profiles/{name}/jobs/{job_id}/resume", response_class=HTMLResponse)
async def partial_profile_cron_resume(request: Request, name: str, job_id: str):
    hermes_home = settings.profiles_dir / name
    if not hermes_home.is_dir():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    jobs = get_cron_jobs(hermes_home=hermes_home)
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job and job.get("state") != "paused":
        raise HTTPException(status_code=409, detail="Job is not paused")
    result = await cron_actions.resume_job(job_id, hermes_home=hermes_home)
    error = result["error"] if not result["success"] else None
    cron_jobs = get_cron_jobs(hermes_home=hermes_home)
    cron_output_jobs = get_all_cron_output_jobs(hermes_home=hermes_home)
    return templates.TemplateResponse(
        request=request, name="partials/cron.html",
        context=_cron_partial_ctx(cron_jobs, cron_output_jobs, profile_name=name, action_error=error),
    )
