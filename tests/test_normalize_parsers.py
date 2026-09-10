import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import normalize_findings as nf
from fingerprint import CONFIDENCES, DIMENSIONS, EFFORTS, SEVERITIES

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "raw"
REPO = "/r"

FAMILY = {"osv-scanner.json": "osv."}

# the parsers this file covers; newer parsers have their own fixtures/tests
COVERED = [
    "ruff.json", "mypy.json", "bandit.json", "semgrep.json", "eslint.json", "tsc.txt",
    "madge.json", "gosec.json", "staticcheck.json", "govet.json", "govulncheck.json",
    "clippy.json", "cargo-audit.json", "swiftlint.json", "cppcheck.xml", "gitleaks.json",
    "osv-scanner.json", "npm-audit.json",
]


def run_parser(fname):
    mode, fn = nf.PARSERS[fname]
    content = (FIXTURES / fname).read_text()
    data = json.loads(content) if mode == "json" else content
    return list(fn(data, REPO) or [])


@pytest.mark.parametrize("fname", COVERED)
def test_parser_produces_valid_findings(fname):
    assert fname in nf.PARSERS
    assert (FIXTURES / fname).exists(), f"missing fixture for {fname}"
    out = run_parser(fname)
    assert out, f"{fname}: parser produced no findings"
    family = FAMILY.get(fname, Path(fname).stem + ".")
    for f in out:
        assert f["dimension"] in DIMENSIONS
        assert f["severity"] in SEVERITIES
        assert f["confidence"] in CONFIDENCES
        assert f["effort"] in EFFORTS
        assert f["rule"].startswith(family), f["rule"]
        assert f["fingerprint"].startswith("sha256:")
        assert f["title"] and f["description"] is not None
        for l in f["locations"]:
            assert not l["path"].startswith("/"), l["path"]


def by_rule(fname):
    return {f["rule"]: f for f in run_parser(fname)}


def test_bandit_severity_and_confidence():
    r = by_rule("bandit.json")
    assert r["bandit.B602"]["severity"] == "P1"
    assert r["bandit.B301"]["severity"] == "P2"
    assert r["bandit.B301"]["confidence"] == "high"
    assert r["bandit.B301"]["locations"][0]["path"] == "src/load.py"
    assert r["bandit.B301"]["locations"][0]["startLine"] == 2


def test_semgrep_severity():
    r = by_rule("semgrep.json")
    assert r["semgrep.eval-detected"]["severity"] == "P1"
    assert r["semgrep.open-never-closed"]["severity"] == "P2"
    assert r["semgrep.eval-detected"]["locations"][0]["snippet"] == "eval(user_input)"


def test_npm_audit_severity():
    r = by_rule("npm-audit.json")
    assert r["npm-audit.minimist"]["severity"] == "P0"
    assert r["npm-audit.lodash"]["severity"] == "P2"


def test_eslint_severity():
    r = by_rule("eslint.json")
    assert r["eslint.no-unused-vars"]["severity"] == "P2"
    assert r["eslint.semi"]["severity"] == "P3"
    assert r["eslint.semi"]["locations"][0]["path"] == "src/app.js"


def test_gosec_severity_and_line_range():
    r = by_rule("gosec.json")
    assert r["gosec.G204"]["severity"] == "P1"
    assert r["gosec.G104"]["severity"] == "P3"
    assert r["gosec.G104"]["locations"][0]["startLine"] == 17


def test_staticcheck_dimension_split():
    r = by_rule("staticcheck.json")
    assert (r["staticcheck.SA4006"]["severity"], r["staticcheck.SA4006"]["dimension"]) == ("P2", "correctness")
    assert (r["staticcheck.ST1005"]["severity"], r["staticcheck.ST1005"]["dimension"]) == ("P3", "readability")


def test_govet_parses_pretty_printed_stream():
    r = by_rule("govet.json")
    assert set(r) == {"govet.printf", "govet.unusedresult"}
    assert r["govet.printf"]["locations"][0] == {
        "path": "pkg/x.go", "startLine": 12, "endLine": 12, "snippetHash": None, "snippet": None}


def test_govulncheck_reachability():
    r = by_rule("govulncheck.json")
    assert r["govulncheck.GO-2023-1840"]["severity"] == "P1"
    assert "CALLED" in r["govulncheck.GO-2023-1840"]["description"]
    assert r["govulncheck.GO-2024-0001"]["severity"] == "P2"


def test_clippy_levels_and_noise_filter():
    out = run_parser("clippy.json")
    assert len(out) == 2
    r = {f["rule"]: f for f in out}
    assert r["clippy.unused_variables"]["severity"] == "P3"
    assert r["clippy.clippy::unwrap_used"]["severity"] == "P2"
    assert r["clippy.unused_variables"]["locations"][0]["path"] == "src/main.rs"


def test_cppcheck_mapping():
    out = run_parser("cppcheck.xml")
    assert len(out) == 2  # the location-less 'information' entry is dropped
    r = {f["rule"]: f for f in out}
    np = r["cppcheck.nullPointer"]
    assert (np["severity"], np["dimension"], np["confidence"]) == ("P1", "correctness", "high")
    assert [l["path"] for l in np["locations"]] == ["src/main.c", "src/main.c"]
    uv = r["cppcheck.unreadVariable"]
    assert (uv["severity"], uv["dimension"], uv["confidence"]) == ("P3", "readability", "medium")


def test_mypy_drops_notes():
    out = run_parser("mypy.json")
    assert len(out) == 1
    assert out[0]["rule"] == "mypy.return-value"
    assert out[0]["locations"][0]["path"] == "src/a.py"


def test_tsc_regex():
    r = by_rule("tsc.txt")
    assert set(r) == {"tsc.TS2322", "tsc.TS7006"}
    assert r["tsc.TS2322"]["locations"][0]["startLine"] == 12


def test_gitleaks_is_p0_and_redacted():
    out = run_parser("gitleaks.json")
    assert out[0]["severity"] == "P0"
    assert "REDACTED" not in out[0]["description"]
    assert out[0]["locations"][0]["path"] == "config/settings.py"


def test_osv_scanner_scores_vector():
    out = run_parser("osv-scanner.json")
    assert out[0]["severity"] == "P1"
    assert out[0]["locations"][0]["path"] == "package-lock.json"


def test_madge_cycle_is_design():
    out = run_parser("madge.json")
    assert out[0]["dimension"] == "design"
    assert "src/a.ts -> src/b.ts -> src/a.ts" in out[0]["description"]


def test_cargo_audit_and_swiftlint():
    ca = run_parser("cargo-audit.json")
    assert ca[0]["rule"] == "cargo-audit.RUSTSEC-2021-0124"
    assert "tokio" in ca[0]["recommendation"]
    sl = by_rule("swiftlint.json")
    assert sl["swiftlint.force_unwrapping"]["severity"] == "P2"
    assert sl["swiftlint.line_length"]["severity"] == "P3"


def _mk(rule, severity, i):
    return nf.new_finding(dimension="readability", rule=rule, source="t", severity=severity,
                          title=f"{rule} {i}", description="d",
                          locations=[{"path": f"src/f{i % 3}.py", "startLine": i}])


def test_cap_floods_rolls_remainder_into_census():
    flood = [_mk("ruff.E501", "P3", i) for i in range(26)]
    keep = [_mk("ruff.F841", "P3", i) for i in range(25)]
    out = nf.cap_floods(flood + keep)
    census = [f for f in out if f["rule"].endswith(".rollup-census")]
    assert len(census) == 1
    c = census[0]
    assert c["rule"] == "ruff.E501.rollup-census"
    assert (c["severity"], c["effort"], c["locations"]) == ("P3", "M", [])
    assert "26 total occurrences (1 beyond the 25 listed)" in c["title"]
    assert sum(1 for f in out if f["rule"] == "ruff.E501") == 25
    assert sum(1 for f in out if f["rule"] == "ruff.F841") == 25


def test_cap_floods_never_caps_p0_p1():
    out = nf.cap_floods([_mk("bandit.B602", "P1", i) for i in range(40)])
    assert len(out) == 40


def test_main_end_to_end_is_idempotent(tmp_path, monkeypatch):
    profile = tmp_path / "repo-profile.json"
    profile.write_text(json.dumps({"repo": REPO, "commit": "abc123", "scope": "."}))
    out = tmp_path / "audit"
    out.mkdir()  # the pipeline creates AUDIT_DIR in Phase 0; main() does not
    argv = ["normalize_findings.py", "--raw", str(FIXTURES),
            "--profile", str(profile), "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    nf.main()
    doc = json.loads((out / "findings.json").read_text())
    assert doc["audit"]["repo"] == REPO
    assert doc["audit"]["commit"] == "abc123"
    assert doc["audit"]["scope"] == "."
    n = len(doc["findings"])
    assert n >= len(nf.PARSERS)
    assert len({f["fingerprint"] for f in doc["findings"]}) == n
    assert all(f["id"] for f in doc["findings"])

    monkeypatch.setattr(sys, "argv", argv)
    nf.main()
    again = json.loads((out / "findings.json").read_text())
    assert len(again["findings"]) == n
