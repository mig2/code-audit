#!/usr/bin/env python3
"""Phase 4: diff findings against a baseline; apply suppressions.

Usage: baseline.py AUDIT_DIR/findings.json [--baseline FILE] [--suppressions FILE]
       [--write-baseline] --out AUDIT_DIR

- baseline FILE defaults to <repo>/.audit-baseline.json then AUDIT_DIR/baseline.json
- suppressions FILE: {"suppress": [{"fingerprint": "...", "reason": "..."}|
                                   {"rule": "...", "path_prefix": "...", "reason": "..."}]}
- Findings present in baseline -> status "persisting"
- Baseline entries absent now -> appended as status "fixed" (kept for report/issue sync)
- --write-baseline snapshots current open findings as the new baseline
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fingerprint import load_findings, save_findings, severity_counts  # noqa: E402


def find_baseline(findings_path, explicit):
    if explicit:
        return Path(explicit)

    # try manifest-based auto-discovery
    findings_dir = Path(findings_path).parent
    try:
        from audit_history import previous_audit
        prev = previous_audit(findings_dir)
        if prev and (prev / "findings.json").exists():
            return prev / "findings.json"
    except (ImportError, Exception):
        pass

    # fallback to legacy file-path search
    doc = json.loads(Path(findings_path).read_text())
    repo = Path(doc.get("audit", {}).get("repo", "."))
    for cand in (repo / ".audit-baseline.json",
                 Path(findings_path).parent / "baseline.json"):
        if cand.exists():
            return cand
    return None


def matches_suppression(f, rule):
    if "fingerprint" in rule:
        return f["fingerprint"] == rule["fingerprint"]
    ok = True
    if "rule" in rule:
        ok = ok and (f["rule"] == rule["rule"] or
                     f["rule"].startswith(rule["rule"].rstrip("*")))
    if "path_prefix" in rule:
        ok = ok and any(l["path"].startswith(rule["path_prefix"])
                        for l in f["locations"])
    return ok and ("rule" in rule or "path_prefix" in rule)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings_file")
    ap.add_argument("--baseline")
    ap.add_argument("--suppressions")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    fpath = Path(args.findings_file)
    doc = load_findings(fpath)
    findings = doc["findings"]

    # suppressions
    spath = Path(args.suppressions) if args.suppressions else out / "suppressions.json"
    n_supp = 0
    if spath.exists():
        rules = json.loads(spath.read_text()).get("suppress", [])
        for f in findings:
            if f["status"] == "suppressed":
                continue
            for r in rules:
                if matches_suppression(f, r):
                    f["status"] = "suppressed"
                    f["suppressReason"] = r.get("reason", "suppressed by rule")
                    n_supp += 1
                    break

    # baseline diff
    bpath = find_baseline(fpath, args.baseline)
    n_new = n_pers = n_fixed = 0
    if bpath and bpath.exists():
        base = json.loads(bpath.read_text())
        base_fps = {b["fingerprint"]: b for b in base.get("findings", [])}
        current_fps = {f["fingerprint"] for f in findings}
        for f in findings:
            if f["status"] == "suppressed":
                continue
            if f["fingerprint"] in base_fps:
                f["status"] = "persisting"
                prior = base_fps[f["fingerprint"]].get("tracker") or {}
                if prior.get("url") and not (f.get("tracker") or {}).get("url"):
                    f["tracker"] = prior
                n_pers += 1
            else:
                f["status"] = "new"
                n_new += 1
        for fp, b in base_fps.items():
            if fp not in current_fps and b.get("status") != "fixed":
                b = dict(b)
                b["status"] = "fixed"
                findings.append(b)
                n_fixed += 1
    else:
        for f in findings:
            if f["status"] != "suppressed":
                f["status"] = "new"
                n_new += 1
        print("no baseline found — all findings classified 'new'"
              " (use --write-baseline to create one)")

    save_findings(doc, fpath)

    if args.write_baseline:
        snapshot = {
            "schema": doc.get("schema"),
            "audit": doc.get("audit", {}),
            "findings": [
                {"fingerprint": f["fingerprint"], "rule": f["rule"],
                 "severity": f["severity"], "dimension": f["dimension"],
                 "title": f["title"], "status": f["status"],
                 "tracker": f.get("tracker"),
                 "locations": [{"path": l["path"]} for l in f["locations"][:1]]}
                for f in doc["findings"]
                if f["status"] in ("new", "persisting")
            ],
        }
        dest = bpath or (out / "baseline.json")
        Path(dest).write_text(json.dumps(snapshot, indent=2) + "\n")
        print(f"baseline written: {dest} ({len(snapshot['findings'])} open findings)")

    print(f"new {n_new} / persisting {n_pers} / fixed {n_fixed} / suppressed {n_supp}")
    print("open severity counts:", severity_counts(doc["findings"]))


if __name__ == "__main__":
    main()
