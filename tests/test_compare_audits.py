import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_audits
from conftest import write_audit


def _audit(root, name, grade, n_findings, remote):
    findings = {"schema": "1.0", "audit": {}, "findings": [
        {"id": f"CA-2026-{i:04d}", "fingerprint": f"sha256:{name}{i}", "dimension": "security",
         "rule": "x.y", "source": "t", "severity": "P2", "confidence": "high", "effort": "S",
         "title": "t", "description": "", "recommendation": "", "locations": [],
         "status": "new", "suppressReason": None, "relatedFingerprints": [],
         "tracker": {"url": None, "id": None}} for i in range(n_findings)]}
    nar = {"title": name, "tier": "standard", "scorecard": [
        {"dimension": "security", "grade": grade, "assessed": True, "summary": ""}]}
    d = root / name
    write_audit(d, findings, narrative=nar,
                profile={"repo": f"/r/{name}", "remote": remote, "commit": "c", "branch": "main",
                         "languages": [{"language": "python", "loc": 1000}]})
    (d / "metrics.json").write_text(json.dumps({"source_loc": 1000}))
    return d


def test_outliers_and_html(tmp_path, monkeypatch):
    a = _audit(tmp_path, "alpha", "A", 1, "git@x:a.git")
    b = _audit(tmp_path, "beta", "C", 5, "git@x:b.git")
    out = tmp_path / "cmp"
    monkeypatch.setattr(sys, "argv", ["compare_audits.py", str(a), str(b), "--out", str(out)])
    compare_audits.main()

    md = (out / "comparison.md").read_text()
    assert "## Outliers" in md
    assert "| security | **alpha** (A, 1.00/kLOC) | **beta** (C, 5.00/kLOC) |" in md
    html = (out / "comparison.html").read_text()
    assert "<table>" in html and "<h2>Outliers" in html


def test_trend_mode_has_no_outliers(tmp_path, monkeypatch):
    a = _audit(tmp_path, "202601", "B", 3, "git@x:same.git")
    b = _audit(tmp_path, "202602", "A", 1, "git@x:same.git")
    out = tmp_path / "cmp"
    monkeypatch.setattr(sys, "argv", ["compare_audits.py", str(a), str(b), "--out", str(out)])
    compare_audits.main()
    md = (out / "comparison.md").read_text()
    assert "## Trend" in md and "## Outliers" not in md
