#!/usr/bin/env python3
"""Phase 5b: render dashboard.html (single-file, interactive).

Usage: render_dashboard.py AUDIT_DIR [--history DIR1 DIR2 ...]
--history: earlier audit dirs (each with findings.json) for the trend chart,
           in chronological order; the current AUDIT_DIR is appended last.
For monorepos run against the rollup dir: per-project subdirs are auto-merged
with a 'project' field on each finding.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fingerprint import SEVERITIES, severity_counts  # noqa: E402

TEMPLATE = Path(__file__).parent.parent / "assets" / "dashboard-template.html"


def collect(audit_dir):
    """Findings + hotspots; merges per-project subdirs when present."""
    d = Path(audit_dir)
    findings, hotspots, names = [], [], []
    if (d / "findings.json").exists():
        doc = json.loads((d / "findings.json").read_text())
        findings = doc["findings"]
        names = [d.resolve().name]
        if (d / "metrics.json").exists():
            hotspots = json.loads((d / "metrics.json").read_text()).get("hotspots", [])
    else:
        for sub in sorted(p for p in d.iterdir()
                          if p.is_dir() and (p / "findings.json").exists()):
            doc = json.loads((sub / "findings.json").read_text())
            for f in doc["findings"]:
                f["project"] = sub.name
            findings += doc["findings"]
            names.append(sub.name)
            if (sub / "metrics.json").exists():
                for h in json.loads((sub / "metrics.json").read_text()).get("hotspots", []):
                    h["path"] = f"{sub.name}/{h['path']}"
                    hotspots.append(h)
        hotspots.sort(key=lambda h: -h["score"])
        hotspots = hotspots[:25]
    return findings, hotspots, names


def slim(f):
    keep = ("id", "fingerprint", "dimension", "rule", "source", "severity",
            "confidence", "effort", "title", "status", "project")
    out = {k: f.get(k) for k in keep if f.get(k) is not None}
    out["description"] = (f.get("description") or "")[:1500]
    out["recommendation"] = (f.get("recommendation") or "")[:600]
    out["locations"] = [{"path": l["path"], "startLine": l.get("startLine")}
                        for l in f.get("locations", [])[:4]]
    return out


def build_history_from_manifest(audit_root, current_id):
    """Build history list from audit-history.json for the trend chart."""
    sys.path.insert(0, str(Path(__file__).parent))
    from audit_history import load_history

    audit_root = Path(audit_root)
    history_doc = load_history(audit_root)
    complete = [a for a in history_doc["audits"] if a["status"] == "complete"]
    if len(complete) < 2:
        return []

    result = []
    for a in complete:
        d = audit_root / a["dir"]
        findings, _, _ = collect(d)
        if findings:
            result.append({"label": a["id"][:12], "counts": severity_counts(findings)})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audit_dir")
    ap.add_argument("--history", nargs="*", default=[])
    args = ap.parse_args()
    d = Path(args.audit_dir)
    findings, hotspots, names = collect(d)
    if not findings:
        sys.exit(f"no findings.json found under {d}")

    profile_p = next(iter([p for p in [d / "repo-profile.json"]
                           + [s / "repo-profile.json" for s in d.iterdir() if s.is_dir()]
                           if p.exists()]), None)
    profile = json.loads(profile_p.read_text()) if profile_p else {}
    repo_name = Path(profile.get("repo", d.resolve().name)).name

    history = []
    if args.history:
        for hdir in args.history:
            hp = Path(hdir)
            hf, _, _ = collect(hp)
            history.append({"label": hp.name[:12],
                            "counts": severity_counts(hf)})
        history.append({"label": "current", "counts": severity_counts(findings)})
    else:
        # auto-discover from manifest
        audit_root = d.parent
        history = build_history_from_manifest(audit_root, d.name)

    data = {
        "title": f"{repo_name} — audit console",
        "meta": (f"commit {(profile.get('commit') or '—')[:10]} · "
                 f"{date.today().isoformat()} · "
                 f"{len([f for f in findings if f['status'] in ('new','persisting')])} open / "
                 f"{len(findings)} total findings"
                 + (f" · projects: {', '.join(names)}" if len(names) > 1 else "")),
        "findings": [slim(f) for f in findings],
        "hotspots": hotspots,
        "history": history,
    }
    out = TEMPLATE.read_text().replace("{{TITLE}}", data["title"]).replace(
        "{{DATA}}", json.dumps(data).replace("</", "<\\/"))
    (d / "dashboard.html").write_text(out)
    print(f"wrote {d/'dashboard.html'} ({len(data['findings'])} findings embedded)")


if __name__ == "__main__":
    main()
