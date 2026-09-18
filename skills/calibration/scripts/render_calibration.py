#!/usr/bin/env python3
"""Render calibration.md + calibration.html from calibration.json and calibration-signals.json.

Usage: render_calibration.py AUDIT_DIR
calibration.json is written by Claude (schema in references/report.md); the signals file
comes from calibration_signals.py. Both renderings share the audit report template.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "audit" / "scripts"))
from render_report import md_html, wrap_html  # noqa: E402

LEVELS = {
    "L0": "AI-assisted, not a software engineer",
    "L1": "Junior engineer",
    "L2": "Mid-level engineer",
    "L3": "Senior engineer",
    "L4": "Staff / principal engineer",
}
AREAS = ["abstraction", "configurability", "error-handling", "testing", "tooling-ci",
         "dependencies", "documentation", "operability"]
VERDICTS = ["over-built", "fitted", "under-built"]
CONFIDENCES = ["high", "medium", "low"]
DIRECTIONS = ["under-owned", "over-built", "matched", "mixed"]
EFFORTS = ["S", "M", "L"]


def validate(cal):
    def check(value, allowed, what):
        if value not in allowed:
            sys.exit(f"calibration.json: {what} {value!r} not one of {allowed}")
    for a in cal.get("areas", []):
        check(a.get("area"), AREAS, "area")
        check(a.get("verdict"), VERDICTS, "verdict")
        check(a.get("confidence"), CONFIDENCES, "confidence")
    for key in ("required_level", "evident_level"):
        blk = cal.get(key) or {}
        check(blk.get("level"), list(LEVELS), f"{key}.level")
        check(blk.get("confidence"), CONFIDENCES, f"{key}.confidence")
    gap = cal.get("gap") or {}
    check(gap.get("direction"), DIRECTIONS, "gap.direction")
    for step in gap.get("plan", []):
        check(step.get("effort"), EFFORTS, "gap.plan[].effort")
    nxt = cal.get("next_level")
    if nxt:
        check(nxt.get("level"), list(LEVELS), "next_level.level")


def level_str(blk):
    lvl = blk.get("level")
    s = f"**{lvl}** — {LEVELS.get(lvl, '?')}"
    if blk.get("range"):
        s += f" (range {blk['range']})"
    return s + f" · confidence {blk.get('confidence', '?')}"


def _bullets(items):
    return [f"- {x}" for x in items] or ["- _(none)_"]


def signals_appendix(sig):
    if not sig:
        return ["_calibration-signals.json not available_"]
    L = []

    def line(name, blk, *pairs):
        if not blk:
            L.append(f"- **{name}:** not available")
            return
        parts = []
        for label, key in pairs:
            v = blk.get(key)
            if isinstance(v, dict) and "count" in v:
                v = v["count"]
            elif isinstance(v, list):
                v = len(v)
            parts.append(f"{label} {v}")
        L.append(f"- **{name}:** " + " · ".join(parts))

    line("Size", sig.get("size"), ("source LOC", "source_loc"), ("test LOC", "test_loc"),
         ("files", "file_count"), ("service", "is_service"))
    line("Indirection", sig.get("indirection"), ("interfaces", "interfaces"),
         ("≤1-impl interfaces", "single_impl_interfaces"), ("pattern-named files", "pattern_named_files"),
         ("DI frameworks", "di_frameworks"), ("layers/kLOC", "layers_per_kloc"))
    line("Config surface", sig.get("config_surface"), ("env reads", "env_reads"),
         ("config files", "config_files"), ("CLI flags", "cli_flags"), ("feature flags", "feature_flags"))
    line("Error handling", sig.get("error_handling"), ("try blocks", "try_blocks"),
         ("broad catches", "broad_catches"), ("empty catches", "empty_catches"),
         ("error boundary", "error_boundary"), ("logging calls", "logging_calls"),
         ("print debugging", "print_debugging"))
    line("Testing", sig.get("testing"), ("test files", "test_files"), ("test/source", "test_to_source_ratio"),
         ("asserts/file", "assertions_per_test_file"), ("mocks/file", "mocks_per_test_file"),
         ("mirror ratio", "mirror_ratio"), ("no-assert tests", "no_assert_tests"),
         ("critical untested", "critical_untested"))
    line("Dependencies", sig.get("dependencies"), ("direct", "direct_total"), ("per kLOC", "per_kloc"),
         ("duplicate purpose", "duplicate_purpose"), ("pinned ratio", "pinned_ratio"),
         ("heavy for purpose", "heavy_for_purpose"))
    line("Documentation", sig.get("documentation"), ("README lines", "readme_lines"),
         ("sections", "readme_sections"), ("architecture doc", "has_architecture_doc"),
         ("comment density", "comment_density"), ("TODOs", "todo_count"))
    line("History", sig.get("history"), ("commits", "commits"), ("authors", "authors"),
         ("first-commit LOC ratio", "first_commit_loc_ratio"), ("median files/commit", "median_files_per_commit"),
         ("AI co-authored", "ai_coauthor_commits"), ("commits/active week", "commits_per_active_week"))
    line("AI-assist markers", sig.get("ai_assist_markers"), ("instruction files", "instruction_files"),
         ("generated headers", "generated_headers"))
    line("Demand drivers", sig.get("demand_drivers"), ("concurrency", "concurrency"),
         ("security surface", "security_surface"), ("data stores", "data_stores"),
         ("deployment artifacts", "deployment"), ("hard spots", "domain_hard_spots"),
         ("public API files", "public_api"))
    pt = sig.get("passthrough")
    if pt:
        fn = pt.get("functions") or {}
        L.append(f"- **Audit metrics:** functions {fn.get('count')} (p90 {fn.get('p90')}, >80 LOC {fn.get('over_80')}) · "
                 f"duplication {pt.get('duplication_percentage')}% · coverage {pt.get('coverage_overall')}% · "
                 f"import cycles {sum((pt.get('import_cycles') or {}).values())}")
    return L


def render_md(cal, sig):
    req, evi, gap = cal.get("required_level", {}), cal.get("evident_level", {}), cal.get("gap", {})
    L = [f"# {cal.get('title', 'Calibration')}\n",
         f"**Date:** {date.today().isoformat()} · **Audit:** `{cal.get('audit_dir', '?')}` · "
         f"**Required owner:** {req.get('level', '?')} · **Evident author:** {evi.get('level', '?')}"
         + (f" ({evi['range']})" if evi.get("range") else "") + "\n"]
    A = L.append
    A("## Purpose\n")
    A(cal.get("purpose", "") + "\n")
    A("## Summary\n")
    A(cal.get("summary", "") + "\n")

    A("## Proportionality by area\n")
    A("| Area | Verdict | Confidence | Evidence |")
    A("|---|---|---|---|")
    for a in cal.get("areas", []):
        A(f"| {a['area']} | **{a['verdict']}** | {a['confidence']} | {len(a.get('evidence', []))} |")
    A("")
    for a in cal.get("areas", []):
        A(f"### {a['area']} — {a['verdict']}\n")
        if a.get("note"):
            A(a["note"] + "\n")
        L.extend(_bullets(a.get("evidence", [])))
        A("")

    A("## Required owner level\n")
    A(level_str(req) + "\n")
    A("**Drivers:**\n")
    L.extend(_bullets(req.get("drivers", [])))
    A("")
    if req.get("note"):
        A(req["note"] + "\n")

    A("## Evident author level\n")
    A(level_str(evi) + "\n")
    A("**Signatures:**\n")
    L.extend(_bullets(evi.get("signatures", [])))
    A("")
    if evi.get("note"):
        A(evi["note"] + "\n")

    nxt = cal.get("next_level")
    if nxt:
        A(f"## What {nxt['level']} would look like\n")
        A(f"_{LEVELS.get(nxt['level'], '?')}_ — the differences, each the gap between what this code does and what the next rung would have done:\n")
        L.extend(f"{i}. {d}" for i, d in enumerate(nxt.get("differences", []), 1))
        A("")
        if nxt.get("cheapest_step"):
            A(f"**Cheapest step toward it:** {nxt['cheapest_step']}\n")

    A("## Gap\n")
    A(f"**Direction:** {gap.get('direction', '?')}\n")
    A(gap.get("summary", "") + "\n")
    if gap.get("risks"):
        A("**Risks:**\n")
        L.extend(_bullets(gap["risks"]))
        A("")
    if gap.get("plan"):
        A("| Step | Why | Effort |")
        A("|---|---|---|")
        for s in gap["plan"]:
            A(f"| {s.get('step', '')} | {s.get('why', '')} | {s.get('effort', '')} |")
        A("")

    A("## Strengths\n")
    L.extend(_bullets(cal.get("strengths", [])))
    A("")
    A("## Caveats\n")
    A(cal.get("caveats", "") + "\n")
    A("## Signals appendix\n")
    L.extend(signals_appendix(sig))
    A("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audit_dir")
    args = ap.parse_args()
    d = Path(args.audit_dir)
    cal_p = d / "calibration.json"
    if not cal_p.exists():
        sys.exit(f"missing {cal_p}")
    cal = json.loads(cal_p.read_text())
    validate(cal)
    sig_p = d / "calibration-signals.json"
    sig = json.loads(sig_p.read_text()) if sig_p.exists() else None
    md = render_md(cal, sig)
    (d / "calibration.md").write_text(md)
    repo_name = Path((sig or {}).get("repo") or d.resolve().parent.parent.name).name
    (d / "calibration.html").write_text(wrap_html(cal.get("title", "Calibration"), repo_name, md_html(md)))
    print(f"wrote {d/'calibration.md'} and {d/'calibration.html'}")


if __name__ == "__main__":
    main()
