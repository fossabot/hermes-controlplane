"""Read-only observer for Hermes state — profiles, sessions, systemd."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from hermes_controlplane.config import settings


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ProfileSummary:
    name: str
    exists: bool = True
    systemd_state: str = "unknown"
    model: str | None = None
    provider: str | None = None
    last_session_id: str | None = None
    last_activity_at: str | None = None
    message_count_recent: int = 0
    session_count: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "exists": self.exists,
            "systemd_state": self.systemd_state,
            "model": self.model,
            "provider": self.provider,
            "last_session_id": self.last_session_id,
            "last_activity_at": self.last_activity_at,
            "message_count_recent": self.message_count_recent,
            "session_count": self.session_count,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


@dataclass
class SessionInfo:
    id: str
    source: str
    model: str | None
    started_at: str
    ended_at: str | None
    message_count: int
    tool_call_count: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    reasoning_tokens: int
    estimated_cost_usd: float
    cost_status: str | None
    title: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "model": self.model,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "message_count": self.message_count,
            "tool_call_count": self.tool_call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "cost_status": self.cost_status,
            "title": self.title,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_to_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _parse_model_provider_from_yaml(config_path: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {"model": None, "provider": None}
    if not config_path.exists():
        return result
    try:
        text = config_path.read_text()
        in_model_block = False
        for raw_line in text.splitlines():
            if raw_line.startswith("model:"):
                in_model_block = True
                continue
            if in_model_block and raw_line and not raw_line.startswith((" ", "\t")):
                in_model_block = False
            stripped = raw_line.strip()
            if not in_model_block:
                continue
            if stripped.startswith("default:") and result["model"] is None:
                value = stripped.split(":", 1)[1].strip().strip("'\"")
                if value:
                    result["model"] = value
            elif stripped.startswith("provider:") and result["provider"] is None:
                value = stripped.split(":", 1)[1].strip().strip("'\"")
                if value:
                    result["provider"] = value
    except Exception:
        pass
    return result


def _read_profile_config(profile_dir: Path) -> dict[str, str | None]:
    config = _parse_model_provider_from_yaml(settings.hermes_home / "config.yaml")
    profile_config = _parse_model_provider_from_yaml(profile_dir / "config.yaml")
    return {
        "model": profile_config.get("model") or config.get("model"),
        "provider": profile_config.get("provider") or config.get("provider"),
    }


async def _query_systemd_state(service_name: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "is-active", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return stdout.decode().strip() or "unknown"
    except Exception:
        return "unknown"


def _ro_uri(db_path: Path) -> str:
    return f"file:{db_path}?mode=ro"


async def _has_column(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table via PRAGMA table_info."""
    rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def _time_filter_clause(
    since: float | None, until: float | None,
    col: str = "started_at",
) -> tuple[str, list]:
    """Build a WHERE clause fragment and params for time filtering."""
    parts: list[str] = []
    params: list[float] = []
    if since is not None:
        parts.append(f"{col} >= ?")
        params.append(since)
    if until is not None:
        parts.append(f"{col} <= ?")
        params.append(until)
    if not parts:
        return "", params
    return "WHERE " + " AND ".join(parts), params


def _time_and_clause(since: float | None, until: float | None, col: str = "started_at") -> tuple[str, list]:
    """Build an AND clause fragment (no WHERE) for appending to existing WHERE."""
    parts: list[str] = []
    params: list[float] = []
    if since is not None:
        parts.append(f"{col} >= ?")
        params.append(since)
    if until is not None:
        parts.append(f"{col} <= ?")
        params.append(until)
    if not parts:
        return "", params
    return "AND " + " AND ".join(parts), params


async def _db_session_stats(db_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "last_session_id": None,
        "last_activity_at": None,
        "message_count_recent": 0,
        "session_count": 0,
        "estimated_cost_usd": 0.0,
    }
    if not db_path.exists():
        return result
    try:
        async with aiosqlite.connect(_ro_uri(db_path), uri=True) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            if not await cur.fetchone():
                return result
            row = await (await db.execute(
                "SELECT id, started_at, message_count FROM sessions "
                "ORDER BY started_at DESC LIMIT 1"
            )).fetchone()
            if row:
                result["last_session_id"] = row[0]
                result["last_activity_at"] = _ts_to_iso(row[1])
                result["message_count_recent"] = row[2] or 0
            row = await (await db.execute(
                "SELECT COUNT(*), COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0) FROM sessions"
            )).fetchone()
            if row:
                result["session_count"] = row[0]
                result["estimated_cost_usd"] = row[1]
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def list_profiles() -> list[str]:
    profiles_dir = settings.profiles_dir
    if not profiles_dir.is_dir():
        return []
    return sorted(
        d.name for d in profiles_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


async def get_profile_summary(name: str) -> ProfileSummary:
    profile_dir = settings.profiles_dir / name
    if not profile_dir.is_dir():
        return ProfileSummary(name=name, exists=False)
    config = _read_profile_config(profile_dir)
    profile_db = profile_dir / "state.db"
    db_path = profile_db if profile_db.exists() else settings.global_state_db
    stats = await _db_session_stats(db_path)
    systemd_state = await _query_systemd_state(f"hermes-gateway-{name}.service")
    if systemd_state == "unknown":
        systemd_state = await _query_systemd_state("hermes-gateway.service")
    return ProfileSummary(
        name=name, exists=True, systemd_state=systemd_state,
        model=config["model"], provider=config["provider"], **stats,
    )


async def get_all_profiles() -> list[dict[str, Any]]:
    names = await list_profiles()
    summaries = await asyncio.gather(*(get_profile_summary(n) for n in names))
    return [s.to_dict() for s in summaries]


async def get_recent_sessions(
    *,
    limit: int = 20,
    offset: int = 0,
    source: str | None = None,
    model: str | None = None,
    since: float | None = None,
    until: float | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Return paginated sessions with filters. Returns {items, total, limit, offset}."""
    target = db_path or settings.global_state_db
    empty = {"items": [], "total": 0, "limit": limit, "offset": offset}
    if not target.exists():
        return empty
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            if not await cur.fetchone():
                return empty

            # Check optional columns
            has_cache_write = await _has_column(db, "sessions", "cache_write_tokens")
            has_auto_reset = await _has_column(db, "sessions", "was_auto_reset")

            cache_write_expr = (
                "COALESCE(cache_write_tokens, 0)"
                if has_cache_write
                else "0"
            )
            auto_reset_expr = (
                "CASE WHEN was_auto_reset = 1 THEN 1 ELSE 0 END, auto_reset_reason"
                if has_auto_reset
                else "0, NULL"
            )

            where_parts: list[str] = []
            params: list[Any] = []
            if source:
                where_parts.append("source = ?")
                params.append(source)
            if model:
                where_parts.append("model = ?")
                params.append(model)
            if since is not None:
                where_parts.append("started_at >= ?")
                params.append(since)
            if until is not None:
                where_parts.append("started_at <= ?")
                params.append(until)

            where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            count_row = await (await db.execute(
                f"SELECT COUNT(*) FROM sessions {where_sql}", params
            )).fetchone()
            total = count_row[0] if count_row else 0

            rows = await (await db.execute(
                f"SELECT id, source, model, started_at, ended_at, "
                f"COALESCE(message_count, 0), COALESCE(tool_call_count, 0), "
                f"COALESCE(input_tokens, 0), COALESCE(output_tokens, 0), "
                f"COALESCE(cache_read_tokens, 0), COALESCE(reasoning_tokens, 0), "
                f"COALESCE(actual_cost_usd, estimated_cost_usd, 0), cost_status, title, "
                f"CASE WHEN ended_at IS NOT NULL THEN CAST(ended_at - started_at AS INTEGER) ELSE NULL END, "
                f"{cache_write_expr}, "
                f"{auto_reset_expr}, "
                f"CASE WHEN ended_at IS NULL "
                f"  AND (strftime('%s','now') - started_at) > 1800 "
                f"  AND (SELECT finish_reason FROM messages WHERE session_id = sessions.id ORDER BY timestamp DESC LIMIT 1) = 'stop' "
                f"THEN 1 ELSE 0 END as is_stale "
                f"FROM sessions {where_sql} "
                f"ORDER BY started_at DESC LIMIT ? OFFSET ?",
                [*params, min(limit, 100), offset],
            )).fetchall()

            items = []
            for r in rows:
                base = SessionInfo(
                    id=r[0], source=r[1], model=r[2],
                    started_at=_ts_to_iso(r[3]), ended_at=_ts_to_iso(r[4]),
                    message_count=r[5], tool_call_count=r[6],
                    input_tokens=r[7], output_tokens=r[8],
                    cache_read_tokens=r[9], reasoning_tokens=r[10],
                    estimated_cost_usd=r[11], cost_status=r[12], title=r[13],
                ).to_dict()
                base["duration_seconds"] = r[14]
                base["cache_write_tokens"] = r[15]
                base["was_auto_reset"] = bool(r[16])
                base["auto_reset_reason"] = r[17]
                base["is_stale"] = bool(r[18])
                items.append(base)

            return {"items": items, "total": total, "limit": limit, "offset": offset}
    except Exception:
        return empty


async def get_filter_options(db_path: Path | None = None) -> dict[str, list[str]]:
    """Return distinct sources and models for filter dropdowns."""
    target = db_path or settings.global_state_db
    if not target.exists():
        return {"sources": [], "models": []}
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            sources = [r[0] for r in await (await db.execute(
                "SELECT DISTINCT source FROM sessions WHERE source IS NOT NULL ORDER BY source"
            )).fetchall()]
            models = [r[0] for r in await (await db.execute(
                "SELECT DISTINCT model FROM sessions WHERE model IS NOT NULL ORDER BY model"
            )).fetchall()]
            return {"sources": sources, "models": models}
    except Exception:
        return {"sources": [], "models": []}


async def get_overview_stats(
    *, since: float | None = None, until: float | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    target = db_path or settings.global_state_db
    defaults = {
        "total_sessions": 0, "total_messages": 0, "total_cost_usd": 0.0,
        "total_input_tokens": 0, "total_output_tokens": 0,
        "total_cache_read_tokens": 0, "total_reasoning_tokens": 0,
        "active_sessions": 0, "distinct_models": 0, "distinct_sources": 0,
        "total_tool_calls": 0, "avg_duration_seconds": None,
        "total_cache_write_tokens": 0, "cache_efficiency_ratio": None,
    }
    if not target.exists():
        return defaults
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            if not await cur.fetchone():
                return defaults
            where_clause, params = _time_filter_clause(since, until)

            # Check optional columns
            has_cache_write = await _has_column(db, "sessions", "cache_write_tokens")
            cache_write_expr = (
                "COALESCE(SUM(COALESCE(cache_write_tokens, 0)), 0)"
                if has_cache_write
                else "0"
            )

            row = await (await db.execute(
                f"SELECT COUNT(*), "
                f"COALESCE(SUM(COALESCE(message_count, 0)), 0), "
                f"COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0), "
                f"COALESCE(SUM(COALESCE(input_tokens, 0)), 0), "
                f"COALESCE(SUM(COALESCE(output_tokens, 0)), 0), "
                f"COALESCE(SUM(COALESCE(cache_read_tokens, 0)), 0), "
                f"COALESCE(SUM(COALESCE(reasoning_tokens, 0)), 0), "
                f"SUM(CASE WHEN ended_at IS NULL THEN 1 ELSE 0 END), "
                f"COUNT(DISTINCT model), "
                f"COUNT(DISTINCT source), "
                f"COALESCE(SUM(COALESCE(tool_call_count, 0)), 0), "
                f"AVG(CASE WHEN ended_at IS NOT NULL THEN ended_at - started_at ELSE NULL END), "
                f"{cache_write_expr} "
                f"FROM sessions {where_clause}",
                params,
            )).fetchone()
            if row:
                total_cache_read = row[5] or 0
                total_input = row[3] or 0
                denom = total_cache_read + total_input
                cache_ratio = (total_cache_read / denom) if denom > 0 else None

                return {
                    "total_sessions": row[0],
                    "total_messages": row[1],
                    "total_cost_usd": round(row[2], 4),
                    "total_input_tokens": total_input,
                    "total_output_tokens": row[4],
                    "total_cache_read_tokens": total_cache_read,
                    "total_reasoning_tokens": row[6],
                    "active_sessions": row[7],
                    "distinct_models": row[8],
                    "distinct_sources": row[9],
                    "total_tool_calls": row[10],
                    "avg_duration_seconds": row[11],
                    "total_cache_write_tokens": row[12] or 0,
                    "cache_efficiency_ratio": cache_ratio,
                }
            return defaults
    except Exception:
        return defaults


async def get_costs_by_model(
    *, since: float | None = None, until: float | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    target = db_path or settings.global_state_db
    if not target.exists():
        return []
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            where_clause, params = _time_filter_clause(since, until)
            rows = await (await db.execute(
                f"SELECT COALESCE(model, 'unknown'), COUNT(*), "
                f"COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0), "
                f"COALESCE(SUM(COALESCE(input_tokens, 0)), 0), "
                f"COALESCE(SUM(COALESCE(output_tokens, 0)), 0), "
                f"COALESCE(SUM(COALESCE(message_count, 0)), 0) "
                f"FROM sessions {where_clause} GROUP BY model ORDER BY 3 DESC",
                params,
            )).fetchall()
            return [
                {
                    "model": r[0], "sessions": r[1], "cost_usd": round(r[2], 4),
                    "input_tokens": r[3], "output_tokens": r[4], "messages": r[5],
                }
                for r in rows
            ]
    except Exception:
        return []


async def get_sessions_by_source(
    *, since: float | None = None, until: float | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    target = db_path or settings.global_state_db
    if not target.exists():
        return []
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            where_clause, params = _time_filter_clause(since, until)
            rows = await (await db.execute(
                f"SELECT source, COUNT(*), "
                f"COALESCE(SUM(COALESCE(message_count, 0)), 0), "
                f"COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0) "
                f"FROM sessions {where_clause} GROUP BY source ORDER BY 2 DESC",
                params,
            )).fetchall()
            return [
                {"source": r[0], "sessions": r[1], "messages": r[2], "cost_usd": round(r[3], 4)}
                for r in rows
            ]
    except Exception:
        return []


async def get_hourly_activity(
    *, since: float | None = None, until: float | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    target = db_path or settings.global_state_db
    zeros = [{"hour": h, "messages": 0} for h in range(24)]
    if not target.exists():
        return zeros
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            )
            if not await cur.fetchone():
                return zeros
            where_clause, params = _time_filter_clause(since, until, col="timestamp")
            rows = await (await db.execute(
                f"SELECT CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) as hour, "
                f"COUNT(*) FROM messages {where_clause} GROUP BY hour ORDER BY hour",
                params,
            )).fetchall()
            hour_map = {r[0]: r[1] for r in rows}
            return [{"hour": h, "messages": hour_map.get(h, 0)} for h in range(24)]
    except Exception:
        return zeros


async def get_session_detail(
    session_id: str, *, db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return full session row as dict, or None if not found.

    Includes duration_seconds, was_auto_reset, auto_reset_reason, cache_write_tokens.
    Gracefully handles missing optional columns via _has_column().
    """
    target = db_path or settings.global_state_db
    if not target.exists():
        return None
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            db.row_factory = aiosqlite.Row
            has_cache_write = await _has_column(db, "sessions", "cache_write_tokens")
            has_auto_reset = await _has_column(db, "sessions", "was_auto_reset")

            extra_cols = ""
            if has_cache_write:
                extra_cols += ", COALESCE(cache_write_tokens, 0) as cache_write_tokens"
            else:
                extra_cols += ", 0 as cache_write_tokens"

            if has_auto_reset:
                extra_cols += (
                    ", CASE WHEN was_auto_reset = 1 THEN 1 ELSE 0 END as was_auto_reset"
                    ", auto_reset_reason"
                )
            else:
                extra_cols += ", 0 as was_auto_reset, NULL as auto_reset_reason"

            row = await (await db.execute(
                f"SELECT id, source, model, started_at, ended_at, "
                f"COALESCE(message_count, 0), COALESCE(tool_call_count, 0), "
                f"COALESCE(input_tokens, 0), COALESCE(output_tokens, 0), "
                f"COALESCE(cache_read_tokens, 0), COALESCE(reasoning_tokens, 0), "
                f"COALESCE(actual_cost_usd, estimated_cost_usd, 0), cost_status, title"
                f"{extra_cols}, "
                f"CASE WHEN ended_at IS NULL "
                f"  AND (strftime('%s','now') - started_at) > 1800 "
                f"  AND (SELECT finish_reason FROM messages WHERE session_id = sessions.id ORDER BY timestamp DESC LIMIT 1) = 'stop' "
                f"THEN 1 ELSE 0 END as is_stale "
                f"FROM sessions WHERE id = ?",
                [session_id],
            )).fetchone()

            if row is None:
                return None

            duration_seconds: int | None = None
            if row["ended_at"] is not None and row["started_at"] is not None:
                duration_seconds = int(row["ended_at"] - row["started_at"])

            return {
                "id": row["id"],
                "source": row["source"],
                "model": row["model"],
                "started_at": _ts_to_iso(row["started_at"]),
                "ended_at": _ts_to_iso(row["ended_at"]),
                "message_count": row[5],
                "tool_call_count": row[6],
                "input_tokens": row[7],
                "output_tokens": row[8],
                "cache_read_tokens": row[9],
                "reasoning_tokens": row[10],
                "estimated_cost_usd": round(row[11], 6),
                "cost_status": row["cost_status"],
                "title": row["title"],
                "cache_write_tokens": row["cache_write_tokens"],
                "was_auto_reset": bool(row["was_auto_reset"]),
                "auto_reset_reason": row["auto_reset_reason"],
                "duration_seconds": duration_seconds,
                "is_stale": bool(row["is_stale"]),
            }
    except Exception:
        return None


async def get_session_messages(
    session_id: str, *, limit: int = 200, db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return messages for a session ordered by created_at ASC, capped at limit."""
    target = db_path or settings.global_state_db
    if not target.exists():
        return []
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            )
            if not await cur.fetchone():
                return []
            rows = await (await db.execute(
                "SELECT id, role, content, timestamp, tool_call_id, tool_calls, tool_name, finish_reason "
                "FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                [session_id, limit],
            )).fetchall()
            return [
                {
                    "id": r[0], "role": r[1], "content": r[2],
                    "created_at": _ts_to_iso(r[3]),
                    "tool_call_id": r[4], "tool_calls": r[5],
                    "tool_name": r[6], "finish_reason": r[7],
                }
                for r in rows
            ]
    except Exception:
        return []


async def get_daily_stats(
    *, days: int = 7,
    since: float | None = None, until: float | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    target = db_path or settings.global_state_db
    if not target.exists():
        return []
    try:
        async with aiosqlite.connect(_ro_uri(target), uri=True) as db:
            if since is not None or until is not None:
                where_clause, params = _time_filter_clause(since, until)
            else:
                where_clause = "WHERE started_at >= unixepoch('now', '-' || ? || ' days')"
                params = [days]
            rows = await (await db.execute(
                f"SELECT date(started_at, 'unixepoch', 'localtime') as day, "
                f"COUNT(*), "
                f"COALESCE(SUM(COALESCE(message_count, 0)), 0), "
                f"COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0) "
                f"FROM sessions {where_clause} "
                f"GROUP BY day ORDER BY day",
                params,
            )).fetchall()
            return [
                {"date": r[0], "sessions": r[1], "messages": r[2], "cost_usd": round(r[3], 4)}
                for r in rows
            ]
    except Exception:
        return []
