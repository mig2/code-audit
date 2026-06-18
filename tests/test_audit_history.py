import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_history


def test_load_history_no_file(tmp_audit):
    h = audit_history.load_history(tmp_audit)
    assert h["audits"] == []
    assert "repo" in h


def test_load_history_existing(tmp_audit):
    manifest = {"repo": "test", "remote": "git@x", "audits": [
        {"id": "202606181200", "status": "complete"}
    ]}
    (tmp_audit / "audit-history.json").write_text(json.dumps(manifest))
    h = audit_history.load_history(tmp_audit)
    assert len(h["audits"]) == 1
    assert h["audits"][0]["id"] == "202606181200"


def test_save_history(tmp_audit):
    h = {"repo": "test", "remote": "", "audits": []}
    audit_history.save_history(h, tmp_audit)
    written = json.loads((tmp_audit / "audit-history.json").read_text())
    assert written == h


def test_init_creates_timestamped_dir(tmp_audit):
    result = audit_history.init_audit(tmp_audit, repo="/tmp/repo", remote="git@x")
    assert result.exists()
    assert result.parent == tmp_audit
    assert len(result.name) == 12
    assert result.name.isdigit()


def test_init_adds_manifest_entry(tmp_audit):
    audit_history.init_audit(tmp_audit, repo="/tmp/repo", remote="git@x")
    h = audit_history.load_history(tmp_audit)
    assert len(h["audits"]) == 1
    assert h["audits"][0]["status"] == "in-progress"
    assert h["repo"] == "/tmp/repo"
    assert h["remote"] == "git@x"


def test_init_links_baseline_to_previous(tmp_audit):
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None}
    ]}
    audit_history.save_history(h, tmp_audit)
    (tmp_audit / "202601011000").mkdir()
    result = audit_history.init_audit(tmp_audit, repo="r", remote="")
    h2 = audit_history.load_history(tmp_audit)
    new_entry = h2["audits"][-1]
    assert new_entry["baseline_from"] == "202601011000"


def test_init_no_baseline_on_first_run(tmp_audit):
    audit_history.init_audit(tmp_audit, repo="r", remote="")
    h = audit_history.load_history(tmp_audit)
    assert h["audits"][0]["baseline_from"] is None


import pytest
from conftest import write_audit  # noqa: E402


def test_register_marks_complete(tmp_audit, sample_findings, sample_narrative, sample_profile):
    audit_dir = audit_history.init_audit(tmp_audit, repo="/tmp/repo", remote="git@x")
    write_audit(audit_dir, sample_findings, sample_narrative, sample_profile)
    audit_history.register_audit(audit_dir)
    h = audit_history.load_history(tmp_audit)
    entry = h["audits"][-1]
    assert entry["status"] == "complete"
    assert entry["commit"] == "abc123def456"
    assert entry["branch"] == "main"
    assert entry["tier"] == "standard"


def test_register_missing_dir_fails(tmp_audit):
    with pytest.raises(SystemExit):
        audit_history.register_audit(tmp_audit / "nonexistent")


def test_previous_returns_prior_audit(tmp_audit, sample_findings):
    first = tmp_audit / "202601011000"
    first.mkdir()
    write_audit(first, sample_findings)
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "in-progress",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    (tmp_audit / "202602011000").mkdir()
    audit_history.save_history(h, tmp_audit)
    result = audit_history.previous_audit(tmp_audit / "202602011000")
    assert result == first


def test_previous_returns_none_for_first(tmp_audit):
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "in-progress",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
    ]}
    (tmp_audit / "202601011000").mkdir()
    audit_history.save_history(h, tmp_audit)
    result = audit_history.previous_audit(tmp_audit / "202601011000")
    assert result is None
