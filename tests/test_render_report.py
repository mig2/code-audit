import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_report
from conftest import write_audit


def test_md_html_headings_and_tables():
    md = "# Title\n\nintro **bold**\n\n| A | B |\n|---|---|\n| 1 | `x` |\n\n- item\n"
    out = render_report.md_html(md)
    assert "<h1>Title</h1>" in out
    assert "<p>intro <b>bold</b></p>" in out
    assert "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>" in out
    assert "<tr><td>1</td><td><code>x</code></td></tr>" in out
    assert "</tbody></table>" in out
    assert "<ul>\n<li>item</li>\n</ul>" in out


def test_render_md_tolerates_partial_metrics(sample_findings, sample_narrative):
    md = render_report.render_md(sample_findings, {"hotspots": []}, sample_narrative, {}, {}, {})
    assert "Source LOC: 0" in md


def test_metrics_extras_lines():
    m = {"functions": {"count": 12, "p50": 8, "p90": 40, "max": 130,
                       "over_80": [{"path": "a.py", "name": "big", "line": 3, "loc": 130}]},
         "duplication": {"percentage": 4.2, "clones": 3, "top": []},
         "coverage": {"source": "lcov.info", "overall": 61.0,
                      "by_area": {"src/core": {"pct": 90.0, "lines": 500},
                                  "src/ui": {"pct": 12.0, "lines": 300}}},
         "licenses": {"packages": 40, "by_license": {}, "copyleft": ["x"], "unknown": []},
         "import_cycles": {"python": [["a", "b"]], "note": "n"}}
    lines = render_report.metrics_extras(m)
    assert lines[0].startswith("Functions: 12 · p50 8 / p90 40 / max 130 LOC · >80 LOC: 1 (`a.py:big` 130)")
    assert lines[1] == "Duplication: 4.2% (3 clones)"
    assert lines[2] == "Coverage (lcov.info): 61.0% overall; lowest areas: `src/ui` 12.0%, `src/core` 90.0%"
    assert lines[3] == "Licenses: 40 packages · copyleft: 1"
    assert lines[4] == "Import cycles: 1"
    assert render_report.metrics_extras({}) == []


def test_rollup_writes_html(tmp_path, sample_findings, sample_narrative, monkeypatch):
    root = tmp_path / "audit"
    for name in ("api", "web"):
        write_audit(root / name, sample_findings, narrative=sample_narrative)
    (root / "rollup-narrative.json").write_text(json.dumps(
        {"executive_summary": "Overall fine.", "comparison_notes": "web lags api."}))
    monkeypatch.setattr(sys, "argv", ["render_report.py", str(root), "--rollup"])
    render_report.main()
    assert "| **api** |" in (root / "report.md").read_text()
    html = (root / "report.html").read_text()
    assert "<table>" in html and "web lags api." in html
