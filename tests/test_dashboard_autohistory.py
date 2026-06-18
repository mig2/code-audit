import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_history
import render_dashboard
from conftest import write_audit


def test_auto_history_from_manifest(tmp_audit, sample_findings, sample_profile):
    """Dashboard auto-populates history from manifest when no --history flag."""
    for ts_id, fp in [("202601011000", "sha256:aaa111"), ("202602011000", "sha256:bbb222")]:
        findings = json.loads(json.dumps(sample_findings))  # deep copy
        findings["findings"] = [dict(sample_findings["findings"][0], fingerprint=fp)]
        d = tmp_audit / ts_id
        write_audit(d, findings, profile=sample_profile)

    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "complete",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    audit_history.save_history(h, tmp_audit)

    history = render_dashboard.build_history_from_manifest(tmp_audit, "202602011000")
    assert len(history) == 2
    assert history[0]["label"] == "202601011000"


def test_auto_history_empty_when_single_audit(tmp_audit, sample_findings, sample_profile):
    """No history data when there's only one audit."""
    write_audit(tmp_audit / "202601011000", sample_findings, profile=sample_profile)
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
    ]}
    audit_history.save_history(h, tmp_audit)

    history = render_dashboard.build_history_from_manifest(tmp_audit, "202601011000")
    assert len(history) == 0
