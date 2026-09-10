import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_scanners


def test_purpose_dim_mapping():
    assert run_scanners.purpose_dim("dep-vulns(reachability)") == "dependencies"
    assert run_scanners.purpose_dim("lint+format") == "readability"
    assert run_scanners.purpose_dim("static-analysis") == "correctness"
    assert run_scanners.purpose_dim("toolchain (vet)") == "correctness"
    assert run_scanners.purpose_dim("vcs") is None
    assert run_scanners.purpose_dim("runtime") is None
    assert run_scanners.purpose_dim("issue filing (GitHub)") is None


def test_skips_respect_only_and_ignore_infrastructure(tmp_path, monkeypatch):
    profile = {"repo": str(tmp_path), "languages": []}
    tools = {"tools": {
        "git": {"available": False, "purpose": "vcs", "via_npx": False},
        "gitleaks": {"available": False, "purpose": "secrets", "via_npx": False},
        "ruff": {"available": False, "purpose": "lint+format", "via_npx": False},
        "eslint": {"available": False, "purpose": "lint", "via_npx": True},
    }}
    (tmp_path / "p.json").write_text(json.dumps(profile))
    (tmp_path / "t.json").write_text(json.dumps(tools))
    out = tmp_path / "audit"
    monkeypatch.setattr(sys, "argv", ["run_scanners.py", "--profile", str(tmp_path / "p.json"),
                                      "--tools", str(tmp_path / "t.json"), "--out", str(out),
                                      "--only", "security"])
    run_scanners.main()
    manifest = json.loads((out / "raw" / "_manifest.json").read_text())
    assert [s["tool"] for s in manifest["skipped"]] == ["gitleaks"]
    assert manifest["skipped"][0]["dimension"] == "security"


def test_failed_scan_is_recorded_as_skipped(tmp_path, monkeypatch):
    profile = {"repo": str(tmp_path), "languages": [{"language": "python"}]}
    tools = {"tools": {"ruff": {"available": True, "purpose": "lint+format", "via_npx": False}}}
    (tmp_path / "p.json").write_text(json.dumps(profile))
    (tmp_path / "t.json").write_text(json.dumps(tools))
    out = tmp_path / "audit"
    monkeypatch.setattr(run_scanners, "cmds_for", lambda *a, **k: ([
        ("ruff", "readability", [sys.executable, "-c", "import sys; sys.exit(2)"], "json", tmp_path)], []))
    monkeypatch.setattr(sys, "argv", ["run_scanners.py", "--profile", str(tmp_path / "p.json"),
                                      "--tools", str(tmp_path / "t.json"), "--out", str(out)])
    run_scanners.main()
    manifest = json.loads((out / "raw" / "_manifest.json").read_text())
    assert manifest["ran"] == []
    assert manifest["skipped"][0]["tool"] == "ruff"
    assert manifest["skipped"][0]["reason"].startswith("exit 2")
