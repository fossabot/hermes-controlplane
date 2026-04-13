"""Unit tests for cron_actions.py — all subprocess calls are monkeypatched."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hermes_controlplane import cron_actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode: int = 0, stdout: bytes = b"ok\n", stderr: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# 5.1 — Happy path: correct env dict, correct argv, returns success=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cli_success_env_and_argv(monkeypatch, tmp_path):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _make_proc(returncode=0, stdout=b"scheduled\n", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/hermes")
    # Reset cached value so monkeypatch takes effect
    cron_actions._hermes_bin = None

    result = await cron_actions._run_hermes_cli("run", "job-abc", tmp_path)

    assert result["success"] is True
    assert result["error"] is None
    assert "scheduled" in result["output"]

    # Verify argv contains hermes, cron, action, job_id
    argv = calls[0][0]
    assert argv[0].endswith("hermes") or argv[0] == "/usr/local/bin/hermes"
    assert "cron" in argv
    assert "run" in argv
    assert "job-abc" in argv

    # Verify HERMES_HOME in env
    env = calls[0][1]["env"]
    assert env["HERMES_HOME"] == str(tmp_path)


# ---------------------------------------------------------------------------
# 5.2 — Non-zero exit → success=False, error=<stderr>
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cli_nonzero_exit(monkeypatch, tmp_path):
    async def fake_exec(*args, **kwargs):
        return _make_proc(returncode=1, stdout=b"", stderr=b"job not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/hermes")
    cron_actions._hermes_bin = None

    result = await cron_actions._run_hermes_cli("run", "job-xyz", tmp_path)

    assert result["success"] is False
    assert "job not found" in result["error"]


# ---------------------------------------------------------------------------
# 5.3 — Timeout → success=False, error contains "timeout"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cli_timeout(monkeypatch, tmp_path):
    async def fake_exec(*args, **kwargs):
        proc = _make_proc()
        async def slow_communicate():
            raise asyncio.TimeoutError()
        proc.communicate = slow_communicate
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/hermes")
    cron_actions._hermes_bin = None

    result = await cron_actions._run_hermes_cli("run", "job-abc", tmp_path)

    assert result["success"] is False
    assert "timeout" in result["error"].lower()


# ---------------------------------------------------------------------------
# 5.4 — hermes not found → success=False, error mentions hermes not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cli_hermes_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda _: None)
    cron_actions._hermes_bin = None

    result = await cron_actions._run_hermes_cli("run", "job-abc", tmp_path)

    assert result["success"] is False
    assert result["error"] is not None
    assert "hermes" in result["error"].lower()


# ---------------------------------------------------------------------------
# Public wrappers: run_job, pause_job, resume_job delegate to _run_hermes_cli
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_job_calls_run_action(monkeypatch, tmp_path):
    captured = {}

    async def fake_cli(action, job_id, hermes_home):
        captured["action"] = action
        captured["job_id"] = job_id
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr(cron_actions, "_run_hermes_cli", fake_cli)

    result = await cron_actions.run_job("my-job", tmp_path)
    assert result["success"] is True
    assert captured["action"] == "run"
    assert captured["job_id"] == "my-job"


@pytest.mark.asyncio
async def test_pause_job_calls_pause_action(monkeypatch, tmp_path):
    captured = {}

    async def fake_cli(action, job_id, hermes_home):
        captured["action"] = action
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr(cron_actions, "_run_hermes_cli", fake_cli)

    await cron_actions.pause_job("my-job", tmp_path)
    assert captured["action"] == "pause"


@pytest.mark.asyncio
async def test_resume_job_calls_resume_action(monkeypatch, tmp_path):
    captured = {}

    async def fake_cli(action, job_id, hermes_home):
        captured["action"] = action
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr(cron_actions, "_run_hermes_cli", fake_cli)

    await cron_actions.resume_job("my-job", tmp_path)
    assert captured["action"] == "resume"
