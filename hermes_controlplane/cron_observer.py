"""Read-only observer for Hermes cron jobs — reads jobs.json and output files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_controlplane.config import settings


@dataclass
class CronJob:
    id: str
    name: str
    schedule_display: str
    state: str
    enabled: bool
    deliver: str | None
    model: str | None
    provider: str | None
    script: str | None
    repeat_times: int | None
    repeat_completed: int
    next_run_at: str | None
    last_run_at: str | None
    last_status: str | None
    last_error: str | None
    created_at: str | None
    output_count: int
    prompt_preview: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule_display": self.schedule_display,
            "state": self.state,
            "enabled": self.enabled,
            "deliver": self.deliver,
            "model": self.model,
            "provider": self.provider,
            "script": self.script,
            "repeat_times": self.repeat_times,
            "repeat_completed": self.repeat_completed,
            "next_run_at": self.next_run_at,
            "last_run_at": self.last_run_at,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "output_count": self.output_count,
            "prompt_preview": self.prompt_preview,
        }


@dataclass
class CronOutput:
    job_id: str
    filename: str
    timestamp: str
    size_bytes: int
    preview: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "preview": self.preview,
        }


def _cron_dir(hermes_home: Path | None = None) -> Path:
    return (hermes_home or settings.hermes_home) / "cron"


def _count_outputs(output_dir: Path, job_id: str) -> int:
    job_out = output_dir / job_id
    if not job_out.is_dir():
        return 0
    return sum(1 for f in job_out.iterdir() if f.suffix == ".md")


def _prompt_preview(prompt: str, max_len: int = 120) -> str:
    cleaned = " ".join(prompt.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "..."


def get_cron_jobs(hermes_home: Path | None = None) -> list[dict[str, Any]]:
    """Read all cron jobs from jobs.json."""
    cron = _cron_dir(hermes_home)
    jobs_file = cron / "jobs.json"
    if not jobs_file.exists():
        return []
    try:
        data = json.loads(jobs_file.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    output_dir = cron / "output"
    results = []
    for j in data.get("jobs", []):
        repeat = j.get("repeat") or {}
        schedule = j.get("schedule") or {}
        results.append(CronJob(
            id=j.get("id", ""),
            name=j.get("name", "unnamed"),
            schedule_display=j.get("schedule_display") or schedule.get("display", ""),
            state=j.get("state", "unknown"),
            enabled=j.get("enabled", False),
            deliver=j.get("deliver"),
            model=j.get("model"),
            provider=j.get("provider"),
            script=j.get("script"),
            repeat_times=repeat.get("times"),
            repeat_completed=repeat.get("completed", 0),
            next_run_at=j.get("next_run_at"),
            last_run_at=j.get("last_run_at"),
            last_status=j.get("last_status"),
            last_error=j.get("last_error"),
            created_at=j.get("created_at"),
            output_count=_count_outputs(output_dir, j.get("id", "")),
            prompt_preview=_prompt_preview(j.get("prompt", "")),
        ).to_dict())
    return results


def get_cron_outputs(job_id: str, hermes_home: Path | None = None) -> list[dict[str, Any]]:
    """List output files for a specific cron job, newest first."""
    output_dir = _cron_dir(hermes_home) / "output" / job_id
    if not output_dir.is_dir():
        return []
    results = []
    for f in sorted(output_dir.iterdir(), reverse=True):
        if f.suffix != ".md":
            continue
        try:
            size = f.stat().st_size
            preview = f.read_text(errors="replace")[:300]
        except OSError:
            size = 0
            preview = ""
        # filename: 2026-04-12_19-16-29 → 2026-04-12T19:16:29
        raw = f.stem
        if "_" in raw:
            date_part, time_part = raw.split("_", 1)
            ts = f"{date_part}T{time_part.replace('-', ':')}"
        else:
            ts = raw
        results.append(CronOutput(
            job_id=job_id,
            filename=f.name,
            timestamp=ts,
            size_bytes=size,
            preview=preview,
        ).to_dict())
    return results


def get_cron_output_content(job_id: str, filename: str, hermes_home: Path | None = None) -> str | None:
    """Read the full content of a specific cron output file."""
    f = _cron_dir(hermes_home) / "output" / job_id / filename
    if not f.exists() or not f.is_file():
        return None
    if ".." in filename or "/" in filename:
        return None
    try:
        return f.read_text(errors="replace")
    except OSError:
        return None


def get_all_cron_output_jobs(hermes_home: Path | None = None) -> list[dict[str, Any]]:
    """List all job IDs that have output directories (even if job is no longer in jobs.json)."""
    output_dir = _cron_dir(hermes_home) / "output"
    if not output_dir.is_dir():
        return []
    results = []
    for d in sorted(output_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        outputs = sorted(
            [f for f in d.iterdir() if f.suffix == ".md"],
            key=lambda f: f.name, reverse=True,
        )
        if not outputs:
            continue
        latest = outputs[0]
        results.append({
            "job_id": d.name,
            "output_count": len(outputs),
            "latest_output": latest.name,
            "latest_timestamp": latest.stem.replace("_", " ", 1),
            "latest_size_bytes": latest.stat().st_size,
        })
    return results
