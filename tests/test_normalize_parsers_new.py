import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import normalize_findings as nf
import run_scanners

FIX = Path(__file__).resolve().parent / "fixtures" / "raw"
REPO = "/r"


def run(name):
    mode, fn = nf.PARSERS[name]
    content = (FIX / name).read_text()
    return list(fn(json.loads(content) if mode == "json" else content, REPO) or [])


def by_rule(fs):
    return {f["rule"]: f for f in fs}


def test_radon_cc():
    fs = by_rule(run("radon-cc.json"))
    assert set(fs) == {"radon.cc-D", "radon.cc-F"}
    assert fs["radon.cc-D"]["severity"] == "P2"
    assert fs["radon.cc-F"]["severity"] == "P1"
    assert fs["radon.cc-F"]["dimension"] == "maintainability"
    assert fs["radon.cc-F"]["locations"][0] == {
        "path": "src/app.py", "startLine": 100, "endLine": 199, "snippetHash": None, "snippet": None}


def test_radon_mi():
    fs = run("radon-mi.json")
    assert len(fs) == 1
    assert fs[0]["rule"] == "radon.mi-C" and fs[0]["severity"] == "P3"
    assert fs[0]["locations"][0]["path"] == "src/legacy.py"


def test_cargo_deny():
    fs = by_rule(run("cargo-deny.json"))
    assert fs["cargo-deny.vulnerability"]["dimension"] == "security"
    assert fs["cargo-deny.vulnerability"]["severity"] == "P1"
    assert "tokio 1.20.0" in fs["cargo-deny.vulnerability"]["title"]
    assert fs["cargo-deny.unmaintained"]["severity"] == "P2"
    assert fs["cargo-deny.rejected"]["dimension"] == "dependencies"
    assert fs["cargo-deny.rejected"]["severity"] == "P2"
    assert fs["cargo-deny.duplicate"]["severity"] == "P3"
    assert all(f["locations"][0]["path"] == "Cargo.lock" for f in fs.values())


def test_pmd():
    fs = by_rule(run("pmd.json"))
    assert fs["pmd.AvoidUsingHardCodedIP"]["severity"] == "P3"
    assert fs["pmd.AvoidUsingHardCodedIP"]["dimension"] == "readability"
    assert fs["pmd.EmptyCatchBlock"]["severity"] == "P1"
    assert fs["pmd.EmptyCatchBlock"]["dimension"] == "correctness"
    assert fs["pmd.UseStringBufferForStringAppends"]["dimension"] == "performance"
    assert fs["pmd.EmptyCatchBlock"]["locations"][0]["path"] == "src/main/java/App.java"
    assert fs["pmd.EmptyCatchBlock"]["locations"][0]["startLine"] == 30


def test_jscpd_single_census():
    fs = run("jscpd.json")
    assert len(fs) == 1
    f = fs[0]
    assert f["rule"] == "jscpd.duplication" and f["severity"] == "P3"
    assert "4.5%" in f["title"]
    assert f["locations"][0]["path"] == "src/c.ts"
    assert "src/a.ts:10 ↔ src/b.ts:5 (30 lines)" in f["description"]


def test_jscpd_empty():
    assert list(nf.parse_jscpd({"statistics": {}, "duplicates": []}, REPO)) == []


def test_vulture():
    fs = run("vulture.txt")
    assert [f["rule"] for f in fs] == ["vulture.unused-function", "vulture.unused-import",
                                       "vulture.unreachable-code"]
    assert fs[0]["locations"][0] == {"path": "src/util.py", "startLine": 12, "endLine": 12,
                                     "snippetHash": None, "snippet": None}
    assert all(f["severity"] == "P3" and f["dimension"] == "maintainability" for f in fs)


def test_knip():
    fs = by_rule(run("knip.json"))
    assert set(fs) == {"knip.unused-files", "knip.unused-exports", "knip.unused-types",
                       "knip.unused-dependencies"}
    assert fs["knip.unused-files"]["title"] == "2 unused files"
    assert fs["knip.unused-exports"]["locations"][0] == {
        "path": "src/index.ts", "startLine": 12, "endLine": 12, "snippetHash": None, "snippet": None}
    assert fs["knip.unused-dependencies"]["dimension"] == "dependencies"
    assert "lodash" in fs["knip.unused-dependencies"]["description"]


def test_golangci():
    fs = by_rule(run("golangci-lint.json"))
    assert fs["golangci-lint.errcheck"]["dimension"] == "correctness"
    assert fs["golangci-lint.errcheck"]["severity"] == "P2"
    assert fs["golangci-lint.gosec"]["dimension"] == "security"
    assert fs["golangci-lint.gosec"]["severity"] == "P1"
    assert fs["golangci-lint.revive"]["dimension"] == "readability"
    assert fs["golangci-lint.errcheck"]["locations"][0]["path"] == "internal/io.go"
    assert fs["golangci-lint.errcheck"]["locations"][0]["startLine"] == 22


def test_clang_tidy():
    fs = by_rule(run("clang-tidy.txt"))
    assert len(fs) == 4
    assert fs["clang-tidy.clang-analyzer-deadcode.DeadStores"]["severity"] == "P1"
    assert fs["clang-tidy.bugprone-narrowing-conversions"]["severity"] == "P1"
    assert fs["clang-tidy.modernize-use-auto"]["dimension"] == "readability"
    assert fs["clang-tidy.performance-unnecessary-value-param"]["dimension"] == "performance"
    assert fs["clang-tidy.bugprone-narrowing-conversions"]["locations"][0]["path"] == "src/net.cpp"
    assert fs["clang-tidy.bugprone-narrowing-conversions"]["locations"][0]["startLine"] == 88


@pytest.mark.parametrize("name,source,lockfile,copyleft,unknown,n", [
    ("license-checker.json", "license-checker", "package.json", "some-gpl-lib@1.0.0", "mystery@0.1.0", 4),
    ("pip-licenses.json", "pip-licenses", "requirements.txt", "pyqt5==5.15.9", "weird==0.0.1", 3),
    ("go-licenses.csv", "go-licenses", "go.mod", "github.com/example/copyleft",
     "github.com/example/nolicense", 3),
])
def test_license_inventories(name, source, lockfile, copyleft, unknown, n):
    fs = run(name)
    inv = [f for f in fs if f["rule"] == f"{source}.inventory"]
    assert len(inv) == 1 and inv[0]["severity"] == "INFO"
    assert f"License inventory: {n} packages" in inv[0]["title"]
    assert inv[0]["locations"][0]["path"] == lockfile
    cl = [f for f in fs if f["rule"] == f"{source}.copyleft"]
    assert [f["title"].split(": ")[1].split(" (")[0] for f in cl] == [copyleft]
    assert cl[0]["severity"] == "P1" and cl[0]["dimension"] == "dependencies"
    un = [f for f in fs if f["rule"] == f"{source}.unknown-license"]
    assert [f["title"].split(": ")[1] for f in un] == [unknown]
    assert un[0]["severity"] == "P2"


def test_pip_licenses_env_caveat():
    inv = [f for f in run("pip-licenses.json") if f["rule"].endswith(".inventory")][0]
    assert "current Python environment" in inv["description"]


def test_ruff_format():
    fs = run("ruff-format.txt")
    assert len(fs) == 1
    assert fs[0]["rule"] == "ruff.format-check" and fs[0]["severity"] == "P3"
    assert fs[0]["title"].startswith("2 files")
    assert [l["path"] for l in fs[0]["locations"]] == ["src/app.py", "src/util.py"]
    assert list(nf.parse_ruff_format("12 files already formatted\n", REPO)) == []


def test_swift_format():
    fs = run("swift-format.txt")
    assert [f["rule"] for f in fs] == ["swift-format.OrderedImports", "swift-format.NeverForceUnwrap",
                                       "swift-format.lint"]
    assert fs[1]["locations"][0] == {"path": "Sources/App/Main.swift", "startLine": 40,
                                     "endLine": 40, "snippetHash": None, "snippet": None}
    assert all(f["dimension"] == "readability" and f["severity"] == "P3" for f in fs)


def test_every_parser_has_a_producer(tmp_path, monkeypatch):
    for name in ("package.json", "package-lock.json", "tsconfig.json", "requirements.txt",
                 "compile_commands.json"):
        (tmp_path / name).write_text("{}")
    monkeypatch.setattr(run_scanners.shutil, "which", lambda x: f"/usr/bin/{x}")
    monkeypatch.setattr(run_scanners, "golangci_major", lambda: 2)
    langs = ["python", "typescript", "javascript", "go", "rust", "swift", "c", "cpp", "java"]
    profile = {"repo": str(tmp_path), "scope": ".", "languages": [{"language": l} for l in langs]}
    from check_tools import T
    tools = {"tools": {n: {"available": True, "purpose": p, "via_npx": False}
                       for n, (_, p, _, _) in T.items()}}
    plan, skips = run_scanners.cmds_for(profile, tools, set(), offline=False)
    produced = {f"{tool}.{ext or 'json'}" for tool, _, _, ext, _ in plan}
    produced |= {name for _, name in run_scanners.COLLECT.values()}
    assert skips == []
    assert "staticcheck.json" not in produced  # bundled by golangci-lint
    tools["tools"]["golangci-lint"]["available"] = False
    plan, _ = run_scanners.cmds_for(profile, tools, set(), offline=False)
    produced |= {f"{tool}.{ext or 'json'}" for tool, _, _, ext, _ in plan}
    missing = set(nf.PARSERS) - produced
    assert not missing, missing
