from pathlib import Path

import aiosqlite
import pytest

from hermes_controlplane.observer import (
    ProfileSummary,
    _has_column,
    _ro_uri,
    get_overview_stats,
    get_recent_sessions,
    get_session_detail,
    get_session_messages,
)


def test_ro_uri_uses_sqlite_read_only_mode(tmp_path: Path):
    db = tmp_path / "state.db"
    uri = _ro_uri(db)
    assert uri.startswith("file:")
    assert "mode=ro" in uri


def test_profile_summary_serialization_rounds_cost():
    summary = ProfileSummary(
        name="radar",
        systemd_state="active",
        model="gpt-5.4",
        provider="openai-codex",
        estimated_cost_usd=1.23456789,
    )
    data = summary.to_dict()
    assert data["name"] == "radar"
    assert data["systemd_state"] == "active"
    assert data["estimated_cost_usd"] == 1.234568


# ---------------------------------------------------------------------------
# 4.1 — _has_column
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_has_column_returns_true_when_column_exists(tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("CREATE TABLE sessions (id TEXT, cache_write_tokens INTEGER)")
        await db.commit()
        result = await _has_column(db, "sessions", "cache_write_tokens")
    assert result is True


@pytest.mark.anyio
async def test_has_column_returns_false_when_column_missing(tmp_path):
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("CREATE TABLE sessions (id TEXT)")
        await db.commit()
        result = await _has_column(db, "sessions", "cache_write_tokens")
    assert result is False


# ---------------------------------------------------------------------------
# 4.2 — get_session_detail
# ---------------------------------------------------------------------------

async def _make_sessions_db(tmp_path, *, include_cache_write=True, include_auto_reset=True):
    db_path = tmp_path / "state.db"
    cols = [
        "id TEXT PRIMARY KEY",
        "source TEXT",
        "model TEXT",
        "started_at REAL",
        "ended_at REAL",
        "message_count INTEGER",
        "tool_call_count INTEGER",
        "input_tokens INTEGER",
        "output_tokens INTEGER",
        "cache_read_tokens INTEGER",
        "reasoning_tokens INTEGER",
        "actual_cost_usd REAL",
        "estimated_cost_usd REAL",
        "cost_status TEXT",
        "title TEXT",
    ]
    if include_cache_write:
        cols.append("cache_write_tokens INTEGER")
    if include_auto_reset:
        cols.extend(["was_auto_reset INTEGER", "auto_reset_reason TEXT"])

    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(f"CREATE TABLE sessions ({', '.join(cols)})")
        vals = [
            "sess-1", "cli", "gpt-4", 1_700_000_000.0, 1_700_003_600.0,
            10, 3, 500, 250, 100, 50,
            None, 0.05, "estimated", "Test session",
        ]
        if include_cache_write:
            vals.append(80)
        if include_auto_reset:
            vals.extend([1, "idle"])

        placeholders = ", ".join(["?"] * len(vals))
        await db.execute(f"INSERT INTO sessions VALUES ({placeholders})", vals)
        await db.execute(
            "CREATE TABLE messages (id TEXT, session_id TEXT, role TEXT, content TEXT, "
            "timestamp REAL, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, finish_reason TEXT)"
        )
        await db.commit()
    return db_path


@pytest.mark.anyio
async def test_get_session_detail_returns_dict_for_existing(tmp_path):
    db_path = await _make_sessions_db(tmp_path)
    result = await get_session_detail("sess-1", db_path=db_path)
    assert result is not None
    assert result["id"] == "sess-1"
    assert result["source"] == "cli"
    assert result["model"] == "gpt-4"


@pytest.mark.anyio
async def test_get_session_detail_returns_none_for_unknown(tmp_path):
    db_path = await _make_sessions_db(tmp_path)
    result = await get_session_detail("no-such-id", db_path=db_path)
    assert result is None


@pytest.mark.anyio
async def test_get_session_detail_duration_seconds_correct(tmp_path):
    db_path = await _make_sessions_db(tmp_path)
    result = await get_session_detail("sess-1", db_path=db_path)
    assert result is not None
    assert result["duration_seconds"] == 3600  # 1_700_003_600 - 1_700_000_000


@pytest.mark.anyio
async def test_get_session_detail_graceful_without_cache_write_tokens(tmp_path):
    db_path = await _make_sessions_db(tmp_path, include_cache_write=False)
    result = await get_session_detail("sess-1", db_path=db_path)
    assert result is not None
    assert result["cache_write_tokens"] == 0


# ---------------------------------------------------------------------------
# 4.3 — get_session_messages
# ---------------------------------------------------------------------------

async def _make_messages_db(tmp_path, *, message_count=5):
    db_path = tmp_path / "state.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, model TEXT, "
            "started_at REAL, ended_at REAL, message_count INTEGER, tool_call_count INTEGER, "
            "input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, "
            "reasoning_tokens INTEGER, actual_cost_usd REAL, estimated_cost_usd REAL, "
            "cost_status TEXT, title TEXT)"
        )
        await db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["sess-1", "cli", "gpt-4", 1.0, 2.0, message_count, 0, 0, 0, 0, 0, None, 0.0, None, None],
        )
        await db.execute(
            "CREATE TABLE messages (id TEXT, session_id TEXT, role TEXT, content TEXT, timestamp REAL, "
            "tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, finish_reason TEXT)"
        )
        for i in range(message_count):
            await db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
                [f"msg-{i}", "sess-1", "user" if i % 2 == 0 else "assistant", f"content {i}", float(i),
                 None, None, None, None],
            )
        await db.commit()
    return db_path


@pytest.mark.anyio
async def test_get_session_messages_returns_messages_in_order(tmp_path):
    db_path = await _make_messages_db(tmp_path, message_count=3)
    result = await get_session_messages("sess-1", db_path=db_path)
    assert len(result) == 3
    # Verify ordering by created_at ascending
    assert result[0]["content"] == "content 0"
    assert result[1]["content"] == "content 1"
    assert result[2]["content"] == "content 2"


@pytest.mark.anyio
async def test_get_session_messages_respects_limit(tmp_path):
    db_path = await _make_messages_db(tmp_path, message_count=10)
    result = await get_session_messages("sess-1", limit=5, db_path=db_path)
    assert len(result) == 5


@pytest.mark.anyio
async def test_get_session_messages_empty_for_no_messages(tmp_path):
    db_path = await _make_messages_db(tmp_path, message_count=0)
    result = await get_session_messages("sess-1", db_path=db_path)
    assert result == []


# ---------------------------------------------------------------------------
# 4.4 — get_overview_stats (new fields)
# ---------------------------------------------------------------------------

async def _make_overview_db(tmp_path):
    db_path = tmp_path / "state.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            "CREATE TABLE sessions ("
            "id TEXT, source TEXT, model TEXT, "
            "started_at REAL, ended_at REAL, "
            "message_count INTEGER, tool_call_count INTEGER, "
            "input_tokens INTEGER, output_tokens INTEGER, "
            "cache_read_tokens INTEGER, reasoning_tokens INTEGER, "
            "actual_cost_usd REAL, estimated_cost_usd REAL, "
            "cost_status TEXT, title TEXT"
            ")"
        )
        # completed session: 1000s duration, tool_calls=3
        await db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["s1", "cli", "gpt-4", 1000.0, 2000.0, 10, 3, 400, 200, 100, 50, None, 0.05, None, None],
        )
        # running session (no ended_at): tool_calls=2
        await db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["s2", "cli", "gpt-4", 3000.0, None, 5, 2, 200, 100, 50, 25, None, 0.02, None, None],
        )
        await db.commit()
    return db_path


@pytest.mark.anyio
async def test_overview_stats_total_tool_calls(tmp_path):
    db_path = await _make_overview_db(tmp_path)
    result = await get_overview_stats(db_path=db_path)
    assert result["total_tool_calls"] == 5  # 3 + 2


@pytest.mark.anyio
async def test_overview_stats_avg_duration_excludes_running(tmp_path):
    db_path = await _make_overview_db(tmp_path)
    result = await get_overview_stats(db_path=db_path)
    # Only s1 is completed: 2000 - 1000 = 1000s
    assert result["avg_duration_seconds"] == 1000.0


@pytest.mark.anyio
async def test_overview_stats_cache_efficiency_ratio(tmp_path):
    db_path = await _make_overview_db(tmp_path)
    result = await get_overview_stats(db_path=db_path)
    # total cache_read = 150, total input = 600
    # ratio = 150 / (150 + 600) = 150/750 = 0.2
    assert abs(result["cache_efficiency_ratio"] - 0.2) < 0.001


@pytest.mark.anyio
async def test_overview_stats_cache_efficiency_zero_denominator(tmp_path):
    db_path = tmp_path / "state.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            "CREATE TABLE sessions (id TEXT, source TEXT, model TEXT, "
            "started_at REAL, ended_at REAL, message_count INTEGER, tool_call_count INTEGER, "
            "input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, "
            "reasoning_tokens INTEGER, actual_cost_usd REAL, estimated_cost_usd REAL, "
            "cost_status TEXT, title TEXT)"
        )
        await db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["s1", "cli", "gpt-4", 1.0, 2.0, 0, 0, 0, 0, 0, 0, None, 0.0, None, None],
        )
        await db.commit()
    result = await get_overview_stats(db_path=db_path)
    # Denominator is 0 — must return None or 0.0, no division error
    assert result["cache_efficiency_ratio"] is None or result["cache_efficiency_ratio"] == 0.0


# ---------------------------------------------------------------------------
# get_recent_sessions — new fields
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_recent_sessions_includes_duration(tmp_path):
    db_path = await _make_sessions_db(tmp_path)
    result = await get_recent_sessions(db_path=db_path)
    items = result["items"]
    assert len(items) == 1
    assert items[0]["duration_seconds"] == 3600


@pytest.mark.anyio
async def test_get_recent_sessions_includes_was_auto_reset(tmp_path):
    db_path = await _make_sessions_db(tmp_path)
    result = await get_recent_sessions(db_path=db_path)
    items = result["items"]
    assert items[0]["was_auto_reset"] is True
    assert items[0]["auto_reset_reason"] == "idle"
