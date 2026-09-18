import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "calibration" / "scripts"))
import render_calibration as rc


def _cal(**over):
    cal = {
        "title": "Calibration of demo — 2026-09",
        "audit_dir": ".audit/202609101200",
        "purpose": "A CLI that converts files.",
        "summary": "Fitted overall; testing under-built.",
        "areas": [
            {"area": "abstraction", "verdict": "fitted", "confidence": "high",
             "evidence": ["src/a.py:10 — one module per concern"], "note": "Plain modules."},
            {"area": "testing", "verdict": "under-built", "confidence": "medium",
             "evidence": ["no tests for parse.py"], "note": ""},
        ],
        "required_level": {"level": "L1", "confidence": "high", "drivers": ["no concurrency"], "note": ""},
        "evident_level": {"level": "L0", "range": "L0–L1", "confidence": "medium",
                          "signatures": ["tests mirror implementation"], "note": ""},
        "gap": {"direction": "under-owned", "summary": "Owner needs L1 basics.",
                "risks": ["parser changes are unverified"],
                "plan": [{"step": "Add parse tests", "why": "bug-shaped code", "effort": "S"}]},
        "strengths": ["Small and readable"],
        "caveats": "Signals are heuristic.",
    }
    cal.update(over)
    return cal


def _write(d, cal, signals=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / "calibration.json").write_text(json.dumps(cal))
    if signals is not None:
        (d / "calibration-signals.json").write_text(json.dumps(signals))


def test_render_sections_and_labels(tmp_path, monkeypatch):
    signals = {"repo": "/r/demo", "size": {"source_loc": 100, "test_loc": 0, "file_count": 3, "is_service": False},
               "indirection": {"interfaces": 0, "single_impl_interfaces": [], "pattern_named_files": {"count": 0},
                               "di_frameworks": [], "layers_per_kloc": 0},
               "history": None,
               "passthrough": {"functions": {"count": 5, "p90": 20, "over_80": 0},
                               "duplication_percentage": 1.5, "coverage_overall": None, "import_cycles": {"python": 0}}}
    _write(tmp_path, _cal(), signals)
    monkeypatch.setattr(sys, "argv", ["render_calibration.py", str(tmp_path)])
    rc.main()
    md = (tmp_path / "calibration.md").read_text()
    for h in ("## Purpose", "## Summary", "## Proportionality by area", "## Required owner level",
              "## Evident author level", "## Gap", "## Strengths", "## Caveats", "## Signals appendix"):
        assert h in md
    assert "Junior engineer" in md and "AI-assisted, not a software engineer" in md
    assert "(range L0–L1)" in md
    assert "| testing | **under-built** | medium | 1 |" in md
    assert "| Add parse tests | bug-shaped code | S |" in md
    assert "**History:** not available" in md
    assert "functions 5 (p90 20, >80 LOC 0)" in md
    html = (tmp_path / "calibration.html").read_text()
    assert "<table>" in html and "<h2>Gap</h2>" in html


def test_next_level_section(tmp_path, monkeypatch):
    cal = _cal(next_level={"level": "L1", "differences": ["Structure by domain, not by prompt",
                                                          "Tests that fail when behaviour changes"],
                           "cheapest_step": "Add parse tests"})
    _write(tmp_path, cal)
    monkeypatch.setattr(sys, "argv", ["render_calibration.py", str(tmp_path)])
    rc.main()
    md = (tmp_path / "calibration.md").read_text()
    assert "## What L1 would look like" in md
    assert "_Junior engineer_" in md
    assert "1. Structure by domain, not by prompt" in md and "2. Tests that fail" in md
    assert "**Cheapest step toward it:** Add parse tests" in md
    assert md.index("## What L1 would look like") < md.index("## Gap")


def test_next_level_invalid_level_exits(tmp_path, monkeypatch):
    _write(tmp_path, _cal(next_level={"level": "L9", "differences": []}))
    monkeypatch.setattr(sys, "argv", ["render_calibration.py", str(tmp_path)])
    with pytest.raises(SystemExit):
        rc.main()


def test_renders_without_signals(tmp_path, monkeypatch):
    _write(tmp_path, _cal())
    monkeypatch.setattr(sys, "argv", ["render_calibration.py", str(tmp_path)])
    rc.main()
    assert "calibration-signals.json not available" in (tmp_path / "calibration.md").read_text()


@pytest.mark.parametrize("bad", [
    {"areas": [{"area": "abstraction", "verdict": "meh", "confidence": "high", "evidence": []}]},
    {"areas": [{"area": "vibes", "verdict": "fitted", "confidence": "high", "evidence": []}]},
    {"required_level": {"level": "L9", "confidence": "high"}},
    {"gap": {"direction": "sideways", "plan": []}},
    {"gap": {"direction": "matched", "plan": [{"step": "x", "why": "y", "effort": "XL"}]}},
])
def test_invalid_values_exit(tmp_path, monkeypatch, bad):
    _write(tmp_path, _cal(**bad))
    monkeypatch.setattr(sys, "argv", ["render_calibration.py", str(tmp_path)])
    with pytest.raises(SystemExit) as e:
        rc.main()
    assert e.value.code not in (0, None)
    assert not (tmp_path / "calibration.md").exists()
