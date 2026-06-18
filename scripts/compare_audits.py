#!/usr/bin/env python3
"""Portfolio mode: compare completed audit workspaces.

Usage: compare_audits.py DIR1 DIR2 [...] --out OUTDIR
Auto-detects same-repo trend mode (shared remote) vs cross-repo comparison.
Writes comparison.md (+ comparison.html if narrative present).
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from fingerprint import SEVERITIES, DIMENSIONS, severity_counts  # noqa: E402


def load_dir(d):
    d = Path(d)
    out = {"dir": d, "name": d.resolve().name}
    for k, fn in [("findings", "findings.json"), ("metrics", "metrics.json"),
                  ("narrative", "narrative.json"), ("profile", "repo-profile.json")]:
        p = d / fn
        out[k] = json.loads(p.read_text()) if p.exists() else {}
    out["open"] = [f for f in out["findings"].get("findings", [])
                   if f["status"] in ("new", "persisting")
                   and f["confidence"] != "low"]
    out["open_low"] = [f for f in out["findings"].get("findings", [])
                       if f["status"] in ("new", "persisting")
                       and f["confidence"] == "low"]
    out["kloc"] = max(out["metrics"].get("source_loc", 0), 1) / 1000
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    audits = [load_dir(d) for d in args.dirs]
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    remotes = [a["profile"].get("remote") for a in audits]
    trend = len(audits) >= 2 and len(set(filter(None, remotes))) == 1 and remotes[0]

    nar_p = outdir / "comparison-narrative.json"
    nar = json.loads(nar_p.read_text()) if nar_p.exists() else {}

    L = [f"# Audit comparison — {date.today().isoformat()}\n"]
    A = L.append
    if nar.get("summary"):
        A(nar["summary"] + "\n")
    if trend:
        A(f"_Same-repo trend mode: {remotes[0]}_\n")

    # scorecard matrix
    dims_used = [d for d in DIMENSIONS if any(
        r["dimension"] == d for a in audits for r in a["narrative"].get("scorecard", []))]
    if dims_used:
        A("## Scorecard matrix\n")
        A("| Dimension | " + " | ".join(a["name"] for a in audits) + " |")
        A("|---|" + "---|" * len(audits))
        for dim in dims_used:
            row = []
            for a in audits:
                g = next((r.get("grade", "?") if r.get("assessed", True) else "n/a"
                          for r in a["narrative"].get("scorecard", [])
                          if r["dimension"] == dim), "—")
                row.append(f"**{g}**")
            A(f"| {dim} | " + " | ".join(row) + " |")
        A("")

    # density table
    A("## Findings density (open, per 1k source LOC; low-confidence excluded)\n")
    A("| Audit | LOC | " + " | ".join(SEVERITIES[:4]) + " | total/kLOC | low-conf |")
    A("|---|---|" + "---|" * 6)
    for a in audits:
        sc = Counter(f["severity"] for f in a["open"])
        dens = [f"{sc.get(s,0)/a['kloc']:.2f}" for s in SEVERITIES[:4]]
        A(f"| **{a['name']}** | {int(a['kloc']*1000):,} | " + " | ".join(dens)
          + f" | {len(a['open'])/a['kloc']:.2f} | {len(a['open_low'])} |")
    A("")

    # per-dimension density
    A("## Density by dimension (open findings / kLOC)\n")
    A("| Dimension | " + " | ".join(a["name"] for a in audits) + " |")
    A("|---|" + "---|" * len(audits))
    for dim in DIMENSIONS:
        vals = []
        any_nonzero = False
        for a in audits:
            n = sum(1 for f in a["open"] if f["dimension"] == dim)
            any_nonzero |= n > 0
            vals.append(f"{n/a['kloc']:.2f}")
        if any_nonzero:
            A(f"| {dim} | " + " | ".join(vals) + " |")
    A("")

    # common weaknesses
    rule_repos = defaultdict(dict)
    for a in audits:
        for f in a["open"]:
            base = f["rule"].split(".rollup-census")[0]
            rule_repos[base][a["name"]] = rule_repos[base].get(a["name"], 0) + 1
    common = {r: m for r, m in rule_repos.items() if len(m) >= max(2, len(audits) // 2 + 1)}
    if common and not trend:
        A("## Common weaknesses (rule appears in majority of repos)\n")
        A("| Rule | " + " | ".join(a["name"] for a in audits) + " |")
        A("|---|" + "---|" * len(audits))
        for r, m in sorted(common.items(), key=lambda kv: -sum(kv[1].values()))[:20]:
            A(f"| `{r}` | " + " | ".join(str(m.get(a["name"], 0)) for a in audits) + " |")
        A("\n_Org-level fixes (shared lint config, conventions) beat per-repo issues here._\n")

    # trend mode flows
    if trend:
        A("## Trend (chronological by argument order)\n")
        A("| Audit | " + " | ".join(SEVERITIES) + " | new | fixed |")
        A("|---|" + "---|" * 7)
        prev_fps = None
        for a in audits:
            sc = severity_counts(a["findings"].get("findings", []))
            fps = {f["fingerprint"] for f in a["open"] + a["open_low"]}
            new = len(fps - prev_fps) if prev_fps is not None else "—"
            fixed = len(prev_fps - fps) if prev_fps is not None else "—"
            A(f"| {a['name']} | " + " | ".join(str(sc[s]) for s in SEVERITIES)
              + f" | {new} | {fixed} |")
            prev_fps = fps
        A("")

    # same-language cohort censuses
    primaries = {a["profile"].get("primary_language") for a in audits}
    if len(primaries) == 1 and None not in primaries:
        lang = primaries.pop()
        keys = set()
        for a in audits:
            keys |= set((a["metrics"].get("census_per_kloc", {}).get(lang) or {}).keys())
        if keys:
            A(f"## {lang} cohort censuses (per kLOC)\n")
            A("| Census | " + " | ".join(a["name"] for a in audits) + " |")
            A("|---|" + "---|" * len(audits))
            for k in sorted(keys):
                A(f"| {k} | " + " | ".join(
                    str((a["metrics"].get("census_per_kloc", {}).get(lang) or {}).get(k, 0))
                    for a in audits) + " |")
            A("")
    elif len(primaries) > 1:
        A("_Mixed-language cohort: language-specific census comparison omitted._\n")

    if nar.get("caveats"):
        A("## Caveats\n" + nar["caveats"] + "\n")
    if nar.get("recommendations"):
        A("## Recommendations\n" + nar["recommendations"] + "\n")

    (outdir / "comparison.md").write_text("\n".join(L) + "\n")
    print(f"wrote {outdir/'comparison.md'}"
          + (" (trend mode)" if trend else f" ({len(audits)} repos)"))


if __name__ == "__main__":
    main()
