from pathlib import Path

from hermes_controlplane.observer import ProfileSummary, _ro_uri


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
