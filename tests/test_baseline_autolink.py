import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_history
import baseline
from conftest import write_audit


def test_find_baseline_uses_manifest(tmp_audit, sample_findings):
    """find_baseline discovers prior audit via manifest when no explicit baseline given."""
    prior = tmp_audit / "202601011000"
    write_audit(prior, sample_findings)

    current = tmp_audit / "202602011000"
    current.mkdir()
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "in-progress",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    audit_history.save_history(h, tmp_audit)

    (current / "findings.json").write_text(json.dumps(sample_findings))

    result = baseline.find_baseline(str(current / "findings.json"), None)
    assert result is not None
    assert "202601011000" in str(result)


def test_write_baseline_never_touches_previous_audit(tmp_audit, sample_findings, monkeypatch):
    """--write-baseline writes AUDIT_DIR/baseline.json, not the auto-linked prior findings."""
    prior = tmp_audit / "202601011000"
    write_audit(prior, sample_findings)
    prior_bytes = (prior / "findings.json").read_bytes()

    current = tmp_audit / "202602011000"
    write_audit(current, sample_findings)
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "in-progress",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    audit_history.save_history(h, tmp_audit)

    monkeypatch.setattr(sys, "argv", ["baseline.py", str(current / "findings.json"),
                                      "--write-baseline", "--out", str(current)])
    baseline.main()

    assert (prior / "findings.json").read_bytes() == prior_bytes
    snap = json.loads((current / "baseline.json").read_text())
    assert [f["fingerprint"] for f in snap["findings"]] == ["sha256:aaa111"]
    assert json.loads((current / "findings.json").read_text())["findings"][0]["status"] == "persisting"


def test_find_baseline_explicit_overrides_manifest(tmp_audit, sample_findings):
    """Explicit --baseline flag takes precedence over manifest."""
    explicit = tmp_audit / "explicit-baseline.json"
    explicit.write_text(json.dumps({"findings": []}))
    result = baseline.find_baseline(str(tmp_audit / "findings.json"), str(explicit))
    assert result == explicit
