"""Async subprocess wrapper for hermes cron CLI mutations (run / pause / resume)."""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

# Module-level cache so shutil.which is called at most once per process lifetime.
# Set to None to allow tests to reset via monkeypatch.
_hermes_bin: str | None = None

_TIMEOUT_SECONDS = 15


def _get_hermes_bin() -> str | None:
    """Return the path to the hermes binary, caching after first lookup."""
    global _hermes_bin
    if _hermes_bin is None:
        _hermes_bin = shutil.which("hermes")
    return _hermes_bin


async def _run_hermes_cli(
    action: str,
    job_id: str,
    hermes_home: Path | None = None,
) -> dict[str, Any]:
    """Invoke ``hermes cron <action> <job_id>`` as an async subprocess.

    Returns ``{"success": bool, "output": str, "error": str | None}``.
    """
    hermes = _get_hermes_bin()
    if not hermes:
        return {"success": False, "output": "", "error": "hermes not found on PATH"}

    env = {**os.environ, "HERMES_HOME": str(hermes_home)} if hermes_home else os.environ.copy()

    try:
        proc = await asyncio.create_subprocess_exec(
            hermes, "cron", action, job_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {"success": False, "output": "", "error": "timeout after 15s"}

        if proc.returncode != 0:
            return {
                "success": False,
                "output": stdout.decode(errors="replace"),
                "error": stderr.decode(errors="replace") or f"exit code {proc.returncode}",
            }

        return {
            "success": True,
            "output": stdout.decode(errors="replace"),
            "error": None,
        }
    except Exception as exc:
        return {"success": False, "output": "", "error": str(exc)}


async def run_job(job_id: str, hermes_home: Path | None = None) -> dict[str, Any]:
    """Trigger ``hermes cron run <job_id>``."""
    return await _run_hermes_cli("run", job_id, hermes_home)


async def pause_job(job_id: str, hermes_home: Path | None = None) -> dict[str, Any]:
    """Invoke ``hermes cron pause <job_id>``."""
    return await _run_hermes_cli("pause", job_id, hermes_home)


async def resume_job(job_id: str, hermes_home: Path | None = None) -> dict[str, Any]:
    """Invoke ``hermes cron resume <job_id>``."""
    return await _run_hermes_cli("resume", job_id, hermes_home)
