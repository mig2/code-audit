import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import file_issues


def _f(i, dimension, severity, effort, status="new", title=None):
    return {"id": f"CA-2026-{i:04d}", "fingerprint": f"sha256:{dimension}{severity}{i}",
            "dimension": dimension, "rule": f"t.{i}", "source": "t", "severity": severity,
            "confidence": "high", "effort": effort,
            "title": title or f"{severity} {dimension} finding {i}",
            "description": "desc", "recommendation": "rec",
            "locations": [{"path": f"src/{i}.py", "startLine": i}],
            "language": None, "status": status, "suppressReason": None,
            "relatedFingerprints": [], "tracker": {"url": None, "id": None}}


@pytest.fixture
def findings():
    fs = [_f(1, "security", "P0", "S"),
          _f(2, "security", "P1", "M")]
    fs += [_f(10 + i, "readability", "P2", "XS") for i in range(5)]
    fs += [_f(20, "readability", "P3", "M"),
           _f(30, "testing", "INFO", "XS", title="census only"),
           _f(40, "correctness", "P2", "S", status="fixed"),
           _f(50, "correctness", "P3", "XS", status="suppressed")]
    return fs


def _args(**kw):
    base = {"no_rollup": False, "rollup_threshold": 4}
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_plan_batches_small_p2_p3(findings):
    singles, rollups, fixed = file_issues.build_plan(findings, _args(), {}, None)
    assert {f["severity"] for f in singles} == {"P0", "P1", "P3"}
    assert len(singles) == 3
    assert set(rollups) == {"readability"} and len(rollups["readability"]) == 5
    assert all(f["effort"] in ("XS", "S") for f in rollups["readability"])
    assert [f["id"] for f in fixed] == ["CA-2026-0040"]
    assert not any(f["severity"] == "INFO" or f["status"] == "suppressed"
                   for f in singles + rollups["readability"])


def test_build_plan_no_rollup(findings):
    singles, rollups, _ = file_issues.build_plan(findings, _args(no_rollup=True), {}, None)
    assert rollups == {}
    assert len(singles) == 8


def test_build_plan_threshold(findings):
    _, rollups, _ = file_issues.build_plan(findings, _args(rollup_threshold=6), {}, None)
    assert rollups == {}
    _, rollups, _ = file_issues.build_plan(findings, _args(rollup_threshold=5), {}, None)
    assert len(rollups["readability"]) == 5


def _audit_dir(tmp_path, findings, remote="git@github.com:owner/repo.git"):
    d = tmp_path / "audit"
    d.mkdir()
    (d / "findings.json").write_text(json.dumps({"schema": "1.0", "audit": {}, "findings": findings}))
    (d / "repo-profile.json").write_text(json.dumps(
        {"repo": "/r/repo", "remote": remote, "commit": "abc123"}))
    return d


@pytest.fixture(autouse=True)
def no_tracker_calls(monkeypatch):
    def boom(argv, **kw):
        raise AssertionError(f"tracker CLI invoked in dry run: {argv[:3]}")
    monkeypatch.setattr(file_issues, "sh", boom)


def test_dry_run_plan_output(tmp_path, monkeypatch, capsys, findings):
    d = _audit_dir(tmp_path, findings)
    monkeypatch.setattr(sys, "argv", ["file_issues.py", str(d), "--host", "github",
                                      "--repo", "owner/repo", "--dry-run"])
    file_issues.main()
    out = capsys.readouterr().out
    assert "=== ISSUE PLAN (github owner/repo) ===" in out
    assert "[P0] P0 security finding 1  (create)" in out
    assert "[P1] P1 security finding 2  (create)" in out
    assert "rollup: 5 small fixes (P2/P3 × XS/S)" in out
    assert "census only" not in out
    assert "fixed since baseline: 1 → comment (no close; use --close-fixed)" in out
    assert "labels to ensure:" in out
    for lbl in ("audit", "audit:security", "audit:readability", "audit:rollup", "P0", "P1", "P3"):
        assert lbl in out
    assert "creations: ~7 issues" in out  # 3 singles + 1 rollup + 2 dims + root
    assert "DRY RUN — nothing filed" in out
    assert not (d / "issues-manifest.json").exists()


def test_dry_run_marks_persisting_with_manifest(tmp_path, monkeypatch, capsys, findings):
    findings[0]["status"] = "persisting"
    d = _audit_dir(tmp_path, findings)
    (d / "issues-manifest.json").write_text(json.dumps(
        {"issues": {findings[0]["fingerprint"]: {"number": 7, "url": "u"}}}))
    monkeypatch.setattr(sys, "argv", ["file_issues.py", str(d), "--host", "gitlab",
                                      "--repo", "owner/repo", "--dry-run", "--close-fixed"])
    file_issues.main()
    out = capsys.readouterr().out
    assert "[P0] P0 security finding 1  (persisting→comment)" in out
    assert "→ comment + close" in out


def test_repo_mismatch_exits(tmp_path, monkeypatch, findings):
    d = _audit_dir(tmp_path, findings, remote="git@github.com:someone/else.git")
    monkeypatch.setattr(sys, "argv", ["file_issues.py", str(d), "--host", "github",
                                      "--repo", "owner/repo", "--dry-run"])
    with pytest.raises(SystemExit, match="does not match remote"):
        file_issues.main()


def test_finding_body_permalink_and_marker(findings):
    body = file_issues.finding_body(
        findings[0], {"remote": "https://github.com/owner/repo.git", "commit": "abc123"}, "api")
    assert "https://github.com/owner/repo/blob/abc123/src/1.py#L1" in body
    assert "project api" in body
    assert body.rstrip().endswith("<!-- ca-fp:sha256:securityP01 -->")
