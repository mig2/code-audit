#!/usr/bin/env python3
"""Phase 5a: render report.md + report.html from findings/metrics/narrative.

Usage: render_report.py AUDIT_DIR [--rollup]
--rollup: AUDIT_DIR contains per-project subdirs (each already rendered);
          builds rollup report from their scorecards + rollup-narrative.json.
"""
import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fingerprint import SEVERITIES, SEV_ORDER, DIMENSIONS, severity_counts  # noqa: E402

SEV_COLOR = {"P0": "var(--p0)", "P1": "var(--p1)", "P2": "var(--p2)",
             "P3": "var(--p3)", "INFO": "var(--info)"}
TEMPLATE = Path(__file__).parent.parent / "assets" / "report-template.html"


# ── minimal markdown -> html (paragraphs, lists, bold/italic/code, links) ────
def md_html(text):
    if not text:
        return ""
    out, lines, in_list, in_code = [], text.splitlines(), False, False
    para = []

    def flush():
        nonlocal para
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []

    def inline(s):
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    for ln in lines:
        if ln.strip().startswith("```"):
            if in_code:
                out.append("</pre>")
            else:
                flush()
                out.append("<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(ln))
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", ln)
        if m:
            flush()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + inline(m.group(1)) + "</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if not ln.strip():
            flush()
        else:
            para.append(ln.strip())
    flush()
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=False)


def grade_class(g):
    g = (g or "").strip().upper()
    return "g" + (g[0] if g and g[0] in "ABCDF" else "NA")


def open_findings(findings):
    return [f for f in findings if f["status"] in ("new", "persisting")]


def load(audit_dir):
    d = Path(audit_dir)
    findings = json.loads((d / "findings.json").read_text())
    metrics = json.loads((d / "metrics.json").read_text()) if (d / "metrics.json").exists() else {}
    narrative = json.loads((d / "narrative.json").read_text()) if (d / "narrative.json").exists() else {}
    tools = json.loads((d / "tool-report.json").read_text()) if (d / "tool-report.json").exists() else {}
    profile = json.loads((d / "repo-profile.json").read_text()) if (d / "repo-profile.json").exists() else {}
    manifest_p = d / "raw" / "_manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    return findings, metrics, narrative, tools, profile, manifest


# ───────────────────────────── markdown report ──────────────────────────────
def render_md(fdoc, metrics, nar, tools, profile, manifest):
    F = fdoc["findings"]
    opn = open_findings(F)
    sc = severity_counts(F)
    L = []
    A = L.append
    title = nar.get("title") or f"Audit of {Path(profile.get('repo','repo')).name}"
    A(f"# {title}\n")
    A(f"**Date:** {date.today().isoformat()} · **Tier:** {nar.get('tier','?')} · "
      f"**Commit:** `{(profile.get('commit') or '')[:10]}` · "
      f"**Branch:** {profile.get('branch','?')}\n")
    A(f"**Open findings:** " + " · ".join(f"{s}: {sc[s]}" for s in SEVERITIES) + "\n")

    A("## Executive summary\n")
    A(nar.get("executive_summary", "_(not written)_") + "\n")

    A("## Scorecard\n")
    A("| Dimension | Grade | Open findings | Assessment |")
    A("|---|---|---|---|")
    counts_by_dim = {}
    for f in opn:
        counts_by_dim.setdefault(f["dimension"], {s: 0 for s in SEVERITIES})
        counts_by_dim[f["dimension"]][f["severity"]] += 1
    for row in nar.get("scorecard", []):
        dim = row["dimension"]
        c = counts_by_dim.get(dim, {})
        cstr = " ".join(f"{s}:{c[s]}" for s in SEVERITIES if c.get(s)) or "—"
        grade = row.get("grade", "?") if row.get("assessed", True) else "n/a (tier)"
        A(f"| {dim} | **{grade}** | {cstr} | {row.get('summary','')} |")
    A("")

    if nar.get("top_risks"):
        A("## Top risks\n")
        for i, r in enumerate(nar["top_risks"], 1):
            A(f"**{i}. {r['title']}**  ")
            A(f"{r.get('why','')}  ")
            if r.get("fingerprints"):
                A("Findings: " + ", ".join(f"`{fp[:18]}…`" for fp in r["fingerprints"]) + "\n")
    if nar.get("strengths"):
        A("## Strengths\n")
        for s in nar["strengths"]:
            A(f"- {s}")
        A("")

    A("## Findings by dimension\n")
    by_dim = {}
    for f in F:
        by_dim.setdefault(f["dimension"], []).append(f)
    for dim in DIMENSIONS:
        fs = by_dim.get(dim)
        if not fs and dim not in nar.get("dimension_notes", {}):
            continue
        A(f"### {dim.capitalize()}\n")
        note = nar.get("dimension_notes", {}).get(dim)
        if note:
            A(note + "\n")
        fs_open = sorted([f for f in (fs or []) if f["status"] in ("new", "persisting")],
                         key=lambda f: (SEV_ORDER[f["severity"]],
                                        {"high": 0, "medium": 1, "low": 2}[f["confidence"]]))
        for f in fs_open:
            locs = "; ".join(f"`{l['path']}" + (f":{l['startLine']}`" if l.get("startLine") else "`")
                             for l in f["locations"][:3]) or "—"
            A(f"- **[{f['severity']}/{f['confidence']}]** {f['title']}  ")
            A(f"  {f['id']} · `{f['rule']}` · effort {f['effort']} · {f['status']} · {locs}")
            if f.get("recommendation"):
                A(f"  ↳ {f['recommendation'][:300]}")
        fixed = [f for f in (fs or []) if f["status"] == "fixed"]
        if fixed:
            A(f"\n_Fixed since baseline: {len(fixed)}_")
        A("")

    if nar.get("sequencing"):
        A("## Recommended sequencing\n")
        A(nar["sequencing"] + "\n")

    A("## Metrics appendix\n")
    if metrics:
        A(f"- Source LOC: {metrics.get('source_loc'):,} · test LOC: "
          f"{metrics.get('test_loc'):,} · ratio {metrics.get('test_to_source_ratio')}")
        A(f"- Files: {metrics.get('file_count'):,} · TODO/FIXME: {metrics.get('todo_fixme_count')}")
        if metrics.get("hotspots"):
            A("- Top hotspots (complexity×churn): " + ", ".join(
                f"`{h['path']}`" for h in metrics["hotspots"][:8]))
        for lang, c in (metrics.get("census_per_kloc") or {}).items():
            interesting = {k: v for k, v in c.items() if v}
            if interesting:
                A(f"- {lang} censuses (per kLOC): " +
                  ", ".join(f"{k}={v}" for k, v in interesting.items()))
    A("")

    A("## Audit completeness\n")
    ran = [r["tool"] for r in manifest.get("ran", [])]
    if ran:
        A("Ran: " + ", ".join(sorted(set(ran))) + ".  ")
    skips = manifest.get("skipped", [])
    if skips:
        A("**Not run (coverage gaps):**")
        for s in skips:
            A(f"- {s['tool']}: {s['reason']}" +
              (f" ({s['purpose']})" if s.get("purpose") else ""))
    if nar.get("coverage_notes"):
        A("\n" + nar["coverage_notes"])
    A("")

    suppressed = [f for f in F if f["status"] == "suppressed"]
    if suppressed:
        A("## Suppressed findings\n")
        for f in suppressed:
            A(f"- {f['id']} `{f['rule']}` — {f['title'][:100]} — _{f.get('suppressReason','')}_")
    return "\n".join(L) + "\n"


# ─────────────────────────────── html report ────────────────────────────────
def chip(sev):
    return f'<span class="chip c{sev}">{sev}</span>'


def render_html(fdoc, metrics, nar, tools, profile, manifest):
    F = fdoc["findings"]
    opn = open_findings(F)
    sc = severity_counts(F)
    repo_name = Path(profile.get("repo", "repository")).name

    plate = ""
    for k, v in [("Commit", (profile.get("commit") or "—")[:12]),
                 ("Branch", profile.get("branch") or "—"),
                 ("Tier", nar.get("tier", "—")),
                 ("Date", date.today().isoformat()),
                 ("Languages", ", ".join(l["language"] for l in profile.get("languages", [])[:4]) or "—"),
                 ("Open findings", str(len(opn)))]:
        plate += f'<div><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div></div>'

    total = max(sum(sc.values()), 1)
    sevstrip = "".join(
        f'<span style="width:{100*sc[s]/total:.2f}%;background:{SEV_COLOR[s]}"></span>'
        for s in SEVERITIES if sc[s])
    legend = "".join(
        f'<span><i style="background:{SEV_COLOR[s]}"></i>{s} × {sc[s]}</span>'
        for s in SEVERITIES)

    B = []
    A = B.append

    def section(title, tag, inner):
        A(f'<section><div class="secthead"><h2>{esc(title)}</h2>'
          f'<span class="tag">{esc(tag)}</span></div>{inner}</section>')

    section("Executive summary", "§1", md_html(nar.get("executive_summary", "")))

    counts_by_dim = {}
    for f in opn:
        counts_by_dim.setdefault(f["dimension"], {s: 0 for s in SEVERITIES})
        counts_by_dim[f["dimension"]][f["severity"]] += 1
    rows = ""
    for row in nar.get("scorecard", []):
        dim = row["dimension"]
        c = counts_by_dim.get(dim, {})
        cstr = " · ".join(f"{s} {c[s]}" for s in SEVERITIES if c.get(s)) or "—"
        if row.get("assessed", True):
            g = f'<span class="grade {grade_class(row.get("grade"))}">{esc(row.get("grade","?"))}</span>'
        else:
            g = '<span class="grade gNA">n/a</span>'
        rows += (f"<tr><td><b>{esc(dim)}</b></td><td>{g}</td>"
                 f'<td class="counts">{cstr}</td><td>{esc(row.get("summary",""))}</td></tr>')
    section("Scorecard", "§2",
            f"<table><tr><th>Dimension</th><th>Grade</th><th>Open</th>"
            f"<th>Assessment</th></tr>{rows}</table>")

    if nar.get("top_risks"):
        inner = ""
        fp_index = {f["fingerprint"]: f for f in F}
        for i, r in enumerate(nar["top_risks"], 1):
            links = " ".join(
                f'<a href="#{fp_index[fp]["id"]}"><code>{fp_index[fp]["id"]}</code></a>'
                for fp in r.get("fingerprints", []) if fp in fp_index)
            inner += (f'<div class="risk"><div class="n">{i:02d}</div><div>'
                      f"<h3>{esc(r['title'])}</h3><p>{esc(r.get('why',''))}</p>"
                      f'<p>{links}</p></div></div>')
        section("Top risks", "§3", inner)

    if nar.get("strengths"):
        section("Strengths", "§4",
                "<ul>" + "".join(f"<li>{md_html(s)[3:-4] if md_html(s).startswith('<p>') else esc(s)}</li>"
                                 for s in nar["strengths"]) + "</ul>")

    # findings by dimension
    inner = ""
    by_dim = {}
    for f in F:
        by_dim.setdefault(f["dimension"], []).append(f)
    for dim in DIMENSIONS:
        fs = by_dim.get(dim, [])
        note = nar.get("dimension_notes", {}).get(dim, "")
        if not fs and not note:
            continue
        inner += f'<h3 style="font-size:19px;margin:34px 0 12px">{esc(dim.capitalize())}</h3>'
        inner += md_html(note)
        fs_open = sorted([f for f in fs if f["status"] in ("new", "persisting")],
                         key=lambda f: (SEV_ORDER[f["severity"]],
                                        {"high": 0, "medium": 1, "low": 2}[f["confidence"]]))
        primary = [f for f in fs_open if f["severity"] in ("P0", "P1", "P2")]
        rest = [f for f in fs_open if f["severity"] not in ("P0", "P1", "P2")]

        def card(f):
            locs = "<br>".join(
                f"<code>{esc(l['path'])}" + (f":{l['startLine']}" if l.get("startLine") else "") + "</code>"
                for l in f["locations"][:4])
            rec = (f'<div class="frec"><b>Recommendation</b>{md_html(f["recommendation"])}</div>'
                   if f.get("recommendation") else "")
            return (f'<div class="finding {f["severity"]}" id="{f["id"]}">'
                    f'<div class="fhead">{chip(f["severity"])}'
                    f'<span class="st {f["status"]}">{f["status"]}</span>'
                    f'<span class="fid">{f["id"]} · {esc(f["rule"])}</span>'
                    f"<h3>{esc(f['title'])}</h3></div>"
                    f'<div class="fmeta">confidence {f["confidence"]} · effort {f["effort"]}'
                    f' · source {esc(f["source"])}</div>'
                    f'<div class="floc">{locs}</div>'
                    f'<div class="fbody">{md_html(f["description"][:1200])}</div>{rec}</div>')

        inner += "".join(card(f) for f in primary)
        if rest:
            inner += (f'<details class="dim-extra"><summary>{len(rest)} P3/INFO '
                      f"findings</summary>" + "".join(card(f) for f in rest) + "</details>")
        fixed = [f for f in fs if f["status"] == "fixed"]
        if fixed:
            inner += f'<p class="note">Fixed since baseline: {len(fixed)}</p>'
    section("Findings", "§5", inner)

    if nar.get("sequencing"):
        section("Recommended sequencing", "§6", md_html(nar["sequencing"]))

    # metrics appendix
    if metrics:
        m = metrics
        rows = ""
        for k, v in [("Source LOC", f"{m.get('source_loc',0):,}"),
                     ("Test LOC", f"{m.get('test_loc',0):,}"),
                     ("Test ratio", m.get("test_to_source_ratio")),
                     ("Files", f"{m.get('file_count',0):,}"),
                     ("TODO/FIXME", m.get("todo_fixme_count"))]:
            rows += f"<tr><td><b>{k}</b></td><td>{esc(v)}</td></tr>"
        hs = "".join(f"<tr><td><code>{esc(h['path'])}</code></td><td>{h['loc']}</td>"
                     f"<td>{h['commits_12mo']}</td><td>{h['score']}</td></tr>"
                     for h in m.get("hotspots", [])[:10])
        inner = f"<table>{rows}</table>"
        if hs:
            inner += ("<h3 style='font-size:17px;margin:26px 0 10px'>Hotspots "
                      "(complexity × churn)</h3><table><tr><th>File</th><th>LOC</th>"
                      "<th>Commits 12mo</th><th>Score</th></tr>" + hs + "</table>")
        cen = ""
        for lang, c in (m.get("census_per_kloc") or {}).items():
            items = ", ".join(f"{k} = {v}" for k, v in c.items() if v)
            if items:
                cen += f"<tr><td><b>{esc(lang)}</b></td><td>{esc(items)}</td></tr>"
        if cen:
            inner += ("<h3 style='font-size:17px;margin:26px 0 10px'>Escape-hatch "
                      "censuses (per kLOC)</h3><table>" + cen + "</table>")
        section("Metrics", "§7", inner)

    # completeness
    ran = sorted({r["tool"] for r in manifest.get("ran", [])})
    skips = manifest.get("skipped", [])
    inner = ""
    if ran:
        inner += "<p>Ran: " + ", ".join(f"<code>{esc(t)}</code>" for t in ran) + "</p>"
    if skips:
        inner += "<table><tr><th>Not run</th><th>Reason</th></tr>" + "".join(
            f"<tr><td><code>{esc(s['tool'])}</code></td><td>{esc(s['reason'])}"
            + (f" — {esc(s['purpose'])}" if s.get("purpose") else "") + "</td></tr>"
            for s in skips) + "</table>"
    inner += md_html(nar.get("coverage_notes", ""))
    section("Audit completeness", "§8", inner)

    suppressed = [f for f in F if f["status"] == "suppressed"]
    if suppressed:
        inner = ("<details><summary style='cursor:pointer;font:600 13px var(--mono);"
                 "color:var(--steel)'>" + f"{len(suppressed)} suppressed</summary><ul>"
                 + "".join(f"<li><code>{f['id']}</code> {esc(f['title'][:90])} — "
                           f"<i>{esc(f.get('suppressReason') or '')}</i></li>"
                           for f in suppressed) + "</ul></details>")
        section("Suppressed", "§9", inner)

    tpl = TEMPLATE.read_text()
    title = nar.get("title") or f"Audit — {repo_name}"
    return (tpl.replace("{{TITLE}}", esc(title))
               .replace("{{REPO_NAME}}", esc(repo_name))
               .replace("{{PLATE}}", plate)
               .replace("{{SEVSTRIP}}", sevstrip)
               .replace("{{LEGEND}}", legend)
               .replace("{{BODY}}", "\n".join(B))
               .replace("{{DATE}}", date.today().isoformat()))


# ─────────────────────────────── rollup mode ────────────────────────────────
def render_rollup(audit_dir):
    d = Path(audit_dir)
    nar_p = d / "rollup-narrative.json"
    nar = json.loads(nar_p.read_text()) if nar_p.exists() else {}
    projects = []
    for sub in sorted(p for p in d.iterdir() if p.is_dir() and (p / "findings.json").exists()):
        fdoc = json.loads((sub / "findings.json").read_text())
        pn = json.loads((sub / "narrative.json").read_text()) if (sub / "narrative.json").exists() else {}
        projects.append((sub.name, fdoc, pn))
    L = [f"# Audit rollup — {d.resolve().name}\n",
         f"**Date:** {date.today().isoformat()} · projects: {len(projects)}\n",
         nar.get("executive_summary", ""), "\n## Per-project scorecards\n"]
    dims = [r["dimension"] for _, _, pn in projects for r in pn.get("scorecard", [])]
    dims = [d_ for d_ in DIMENSIONS if d_ in set(dims)]
    L.append("| Project | Open P0/P1/P2/P3 | " + " | ".join(dims) + " |")
    L.append("|---|---|" + "---|" * len(dims))
    for name, fdoc, pn in projects:
        sc = severity_counts(fdoc["findings"])
        grades = {r["dimension"]: (r.get("grade", "?") if r.get("assessed", True) else "n/a")
                  for r in pn.get("scorecard", [])}
        L.append(f"| **{name}** | {sc['P0']}/{sc['P1']}/{sc['P2']}/{sc['P3']} | "
                 + " | ".join(grades.get(d_, "—") for d_ in dims) + " |")
    if nar.get("comparison_notes"):
        L.append("\n## Notes\n" + nar["comparison_notes"])
    L.append("\nPer-project reports: " + ", ".join(f"`{n}/report.md`" for n, _, _ in projects))
    (d / "report.md").write_text("\n".join(L) + "\n")
    print(f"wrote {d/'report.md'} (rollup over {len(projects)} projects)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audit_dir")
    ap.add_argument("--rollup", action="store_true")
    args = ap.parse_args()
    if args.rollup:
        render_rollup(args.audit_dir)
        return
    d = Path(args.audit_dir)
    fdoc, metrics, nar, tools, profile, manifest = load(d)
    (d / "report.md").write_text(render_md(fdoc, metrics, nar, tools, profile, manifest))
    (d / "report.html").write_text(render_html(fdoc, metrics, nar, tools, profile, manifest))
    print(f"wrote {d/'report.md'} and {d/'report.html'}")


if __name__ == "__main__":
    main()
