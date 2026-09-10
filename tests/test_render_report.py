import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
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
