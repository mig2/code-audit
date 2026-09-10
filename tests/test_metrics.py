import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import metrics


def _mini_repo(root):
    pkg = root / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("from app import b\n\ndef small():\n    return b.f()\n")
    big = "def big(x):\n" + "".join(f"    x += {i}\n" for i in range(100)) + "    return x\n"
    (pkg / "b.py").write_text("import app.a\n\n" + big + "\ndef f():\n    return 1  # TODO later\n")
    (root / "main.go").write_text(
        'package main\n\nfunc main() {\n\tif x {\n\t\ty()\n\t}\n}\n\nfunc helper(a int) int {\n\treturn a\n}\n')
    (root / "coverage.xml").write_text(
        '<coverage><packages><package><classes>'
        '<class filename="src/app/a.py"><lines>'
        + "".join(f'<line number="{i}" hits="1"/>' for i in range(1, 151))
        + '</lines></class>'
        '<class filename="src/other/x.py"><lines>'
        + "".join(f'<line number="{i}" hits="0"/>' for i in range(1, 121))
        + '</lines></class>'
        '</classes></package></packages></coverage>')
    raw = root / ".audit" / "raw"
    raw.mkdir(parents=True)
    (raw / "jscpd.json").write_text(json.dumps({
        "statistics": {"total": {"percentage": 12.5, "clones": 1}},
        "duplicates": [{"lines": 40, "firstFile": {"name": "src/app/a.py", "start": 1, "end": 40},
                        "secondFile": {"name": "src/app/b.py", "start": 5, "end": 45}}]}))
    (raw / "pip-licenses.json").write_text(json.dumps([
        {"Name": "requests", "Version": "2.31", "License": "Apache Software License"},
        {"Name": "readline-gpl", "Version": "1.0", "License": "GPL-3.0-only"},
        {"Name": "mystery", "Version": "0.1", "License": "UNKNOWN"}]))
    (raw / "radon-cc.json").write_text(json.dumps({
        "src/app/b.py": [{"type": "function", "name": "big", "complexity": 7, "lineno": 3},
                         {"type": "function", "name": "f", "complexity": 1, "lineno": 105}]}))
    return raw.parent


def test_metrics_end_to_end(tmp_path, monkeypatch):
    out = _mini_repo(tmp_path)
    (tmp_path / "profile.json").write_text(json.dumps({"repo": str(tmp_path), "scope": "."}))
    monkeypatch.setattr(sys, "argv", ["metrics.py", str(tmp_path), "--profile",
                                      str(tmp_path / "profile.json"), "--out", str(out)])
    metrics.main()
    m = json.loads((out / "metrics.json").read_text())

    fn = m["functions"]
    assert fn["method"] == "heuristic"
    assert fn["count"] == 5
    assert fn["max"] >= 100
    assert fn["over_80"][0]["name"] == "big" and fn["over_80"][0]["path"] == "src/app/b.py"
    assert m["files"]["src/app/b.py"]["max_fn_loc"] >= 100
    assert m["files"]["main.go"]["max_fn_loc"] == 5

    assert m["complexity_source"] == {"go": "keyword-proxy", "python": "radon"}
    assert m["files"]["src/app/b.py"]["complexity"] == 8
    assert m["files"]["src/app/b.py"]["complexity_source"] == "radon"
    assert m["files"]["main.go"]["complexity_source"] == "keyword-proxy"

    assert m["duplication"] == {"percentage": 12.5, "clones": 1,
                                "top": [{"a": "src/app/a.py:1-40", "b": "src/app/b.py:5-45", "lines": 40}]}

    lic = m["licenses"]
    assert lic["packages"] == 3
    assert lic["copyleft"] == ["readline-gpl@1.0"]
    assert lic["unknown"] == ["mystery@0.1"]
    assert lic["by_license"]["GPL-3.0-only"] == 1

    cov = m["coverage"]
    assert cov["source"] == "coverage.xml"
    assert cov["overall"] == 55.6
    assert cov["by_area"]["src/app"] == {"pct": 100.0, "lines": 150}
    assert cov["by_area"]["src/other"] == {"pct": 0.0, "lines": 120}
    assert cov["uncovered_areas"] == ["src/other"]

    assert m["import_cycles"]["python"] == [["app.a", "app.b"]]
    assert m["todo_fixme_count"] == 1
    assert m["test_to_source_ratio"] is None or isinstance(m["test_to_source_ratio"], float)


def test_optional_inputs_absent(tmp_path, monkeypatch):
    (tmp_path / "x.py").write_text("def f():\n    pass\n")
    out = tmp_path / ".audit"
    (tmp_path / "profile.json").write_text(json.dumps({"repo": str(tmp_path)}))
    monkeypatch.setattr(sys, "argv", ["metrics.py", str(tmp_path), "--profile",
                                      str(tmp_path / "profile.json"), "--out", str(out)])
    metrics.main()
    m = json.loads((out / "metrics.json").read_text())
    assert m["duplication"] is None and m["licenses"] is None and m["coverage"] is None
    assert m["import_cycles"] == {"python": []}
    assert m["complexity_source"] == {"python": "keyword-proxy"}


def test_lcov_and_brace_functions(tmp_path):
    (tmp_path / "lcov.info").write_text(
        "SF:lib/core/a.ts\nLF:200\nLH:180\nend_of_record\nSF:lib/ui/b.ts\nLF:100\nLH:10\nend_of_record\n")
    cov = metrics.coverage(tmp_path)
    assert cov["source"] == "lcov.info"
    assert cov["by_area"] == {"lib/core": {"pct": 90.0, "lines": 200}, "lib/ui": {"pct": 10.0, "lines": 100}}
    assert cov["uncovered_areas"] == ["lib/ui"]

    ts = ["export function alpha(a: number): number {", "  return a;", "}", "",
          "const beta = async (x) => {", "  await x;", "};", "",
          "class K {", "  private gamma(y): void {", "    if (y) {", "      z();", "    }", "  }", "}",
          "int declared_only(int a);"]
    spans = list(metrics.function_spans("typescript", ts))
    assert [(n, loc) for n, _, loc in spans] == [("alpha", 3), ("beta", 3), ("gamma", 5)]

    c = ["static int add(int a, int b)", "{", "    return a + b;", "}", "",
         "int proto(int a);", "if (x) {", "}"]
    spans = list(metrics.function_spans("c", c))
    assert [(n, loc) for n, _, loc in spans] == [("add", 4)]
