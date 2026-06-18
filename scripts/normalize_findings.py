#!/usr/bin/env python3
"""Phase 2c: normalize raw scanner output into canonical findings.json.

Usage: normalize_findings.py --raw AUDIT_DIR/raw --profile P.json --out AUDIT_DIR
Merges into existing findings.json (idempotent via fingerprints).
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fingerprint import new_finding, load_findings, save_findings  # noqa: E402


def loc(path, line=None, end=None, snippet=""):
    return {"path": path, "startLine": line, "endLine": end or line, "snippet": snippet}


def relpath(p, repo):
    p = str(p).replace("\\", "/")
    repo = str(repo).rstrip("/") + "/"
    return p[len(repo):] if p.startswith(repo) else p.lstrip("./")


# ── per-tool parsers: each yields finding dicts via new_finding ──────────────

def parse_ruff(data, repo):
    sev_map = {"E9": "P2", "F8": "P2"}  # syntax/undefined-name families
    for d in data:
        code = d.get("code") or "ruff"
        fam = code[:2]
        sev = sev_map.get(fam, "P3")
        dim = "correctness" if fam in ("F8", "E9", "B0") else "readability"
        yield new_finding(
            dimension=dim, rule=f"ruff.{code}", source="ruff", severity=sev,
            confidence="high", effort="XS", language="python",
            title=f"{code}: {d.get('message','')}",
            description=d.get("message", ""),
            recommendation=(d.get("fix") or {}).get("message", "") or "See ruff docs for this rule.",
            locations=[loc(relpath(d["filename"], repo),
                           d["location"]["row"], d["end_location"]["row"])],
            snippet_key=f"{code}@{d['location']['row']}")


def parse_mypy(text, repo):
    # mypy --output json => one JSON object per line
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("severity") != "error":
            continue
        yield new_finding(
            dimension="correctness", rule=f"mypy.{d.get('code') or 'error'}",
            source="mypy", severity="P2", confidence="high", effort="S",
            language="python",
            title=f"mypy: {d.get('message','')[:120]}",
            description=d.get("message", ""),
            recommendation="Fix the type error or annotate honestly.",
            locations=[loc(relpath(d.get("file", ""), repo), d.get("line"))],
            snippet_key=f"{d.get('code')}:{d.get('message','')[:80]}")


def parse_bandit(data, repo):
    sev = {"HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}
    conf = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    for d in data.get("results", []):
        yield new_finding(
            dimension="security", rule=f"bandit.{d['test_id']}", source="bandit",
            severity=sev.get(d["issue_severity"], "P3"),
            confidence=conf.get(d["issue_confidence"], "medium"),
            effort="S", language="python",
            title=f"{d['test_id']}: {d['issue_text'][:140]}",
            description=d["issue_text"],
            recommendation=f"See {d.get('more_info','bandit docs')}",
            locations=[loc(relpath(d["filename"], repo), d["line_number"],
                           snippet=d.get("code", ""))])


def parse_semgrep(data, repo):
    sev = {"ERROR": "P1", "WARNING": "P2", "INFO": "P3"}
    for d in data.get("results", []):
        x = d.get("extra", {})
        yield new_finding(
            dimension="security", rule=f"semgrep.{d['check_id'].split('.')[-1]}",
            source="semgrep", severity=sev.get(x.get("severity"), "P2"),
            confidence="high", effort="S",
            title=x.get("message", d["check_id"])[:160],
            description=f"{x.get('message','')}\nRule: {d['check_id']}",
            recommendation=x.get("fix", "") or "See rule documentation.",
            locations=[loc(relpath(d["path"], repo), d["start"]["line"],
                           d["end"]["line"], x.get("lines", ""))])


def parse_eslint(data, repo):
    for f in data:
        for m in f.get("messages", []):
            rule = m.get("ruleId") or "parse-error"
            yield new_finding(
                dimension="readability", rule=f"eslint.{rule}", source="eslint",
                severity="P2" if m.get("severity") == 2 else "P3",
                confidence="high", effort="XS",
                title=f"{rule}: {m.get('message','')[:140]}",
                description=m.get("message", ""),
                recommendation="Fix per rule docs; consider --fix for autofixables.",
                locations=[loc(relpath(f["filePath"], repo), m.get("line"))],
                snippet_key=f"{rule}@{m.get('line')}")


TSC_RE = re.compile(r"^(.+?)\((\d+),\d+\): error (TS\d+): (.*)$")

def parse_tsc(text, repo):
    for line in text.splitlines():
        m = TSC_RE.match(line.strip())
        if not m:
            continue
        path, line_no, code, msg = m.groups()
        yield new_finding(
            dimension="correctness", rule=f"tsc.{code}", source="tsc",
            severity="P2", confidence="high", effort="S", language="typescript",
            title=f"{code}: {msg[:140]}", description=msg,
            recommendation="Resolve the type error.",
            locations=[loc(relpath(path, repo), int(line_no))],
            snippet_key=f"{code}:{msg[:80]}")


def parse_madge(data, repo):
    cycles = data if isinstance(data, list) else []
    for cyc in cycles:
        chain = " -> ".join(cyc)
        yield new_finding(
            dimension="design", rule="madge.circular-dependency", source="madge",
            severity="P2", confidence="high", effort="M",
            title=f"Circular dependency: {chain[:140]}",
            description=f"Import cycle: {chain}",
            recommendation="Break the cycle by extracting the shared piece or inverting a dependency.",
            locations=[loc(cyc[0])], snippet_key=chain)


def parse_gosec(data, repo):
    sev = {"HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}
    conf = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    for d in data.get("Issues", []) or []:
        yield new_finding(
            dimension="security", rule=f"gosec.{d['rule_id']}", source="gosec",
            severity=sev.get(d["severity"], "P2"),
            confidence=conf.get(d["confidence"], "medium"), effort="S", language="go",
            title=f"{d['rule_id']}: {d['details'][:140]}",
            description=d["details"],
            recommendation="See gosec rule documentation.",
            locations=[loc(relpath(d["file"], repo),
                           int(str(d["line"]).split("-")[0]), snippet=d.get("code", ""))])


def parse_staticcheck(text, repo):
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = d.get("code", "SA")
        sev = "P2" if code.startswith(("SA1", "SA2", "SA4", "SA5")) else "P3"
        l = d.get("location", {})
        yield new_finding(
            dimension="correctness" if sev == "P2" else "readability",
            rule=f"staticcheck.{code}", source="staticcheck",
            severity=sev, confidence="high", effort="S", language="go",
            title=f"{code}: {d.get('message','')[:140]}",
            description=d.get("message", ""),
            recommendation="See staticcheck docs.",
            locations=[loc(relpath(l.get("file", ""), repo), l.get("line"))],
            snippet_key=f"{code}:{d.get('message','')[:80]}")


def parse_govet(text, repo):
    # stream of JSON objects keyed by package
    findings = []
    for obj in re.finditer(r"\{.*?\n\}", text, re.S):
        try:
            d = json.loads(obj.group(0))
        except json.JSONDecodeError:
            continue
        for pkg in d.values():
            for check, diags in (pkg or {}).items():
                for diag in diags:
                    posn = diag.get("posn", "::")
                    parts = posn.split(":")
                    findings.append(new_finding(
                        dimension="correctness", rule=f"govet.{check}", source="go vet",
                        severity="P2", confidence="high", effort="S", language="go",
                        title=f"vet/{check}: {diag.get('message','')[:140]}",
                        description=diag.get("message", ""),
                        recommendation="See go vet documentation for this check.",
                        locations=[loc(relpath(parts[0], repo),
                                       int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None)],
                        snippet_key=f"{check}:{diag.get('message','')[:80]}"))
    return findings


def parse_govulncheck(text, repo):
    findings, osvs = [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "osv" in d:
            o = d["osv"]
            osvs[o["id"]] = o
        if "finding" in d:
            f = d["finding"]
            called = bool(f.get("trace") and len(f["trace"]) > 1)
            o = osvs.get(f.get("osv"), {})
            findings.append(new_finding(
                dimension="security", rule=f"govulncheck.{f.get('osv','vuln')}",
                source="govulncheck",
                severity="P1" if called else "P2",
                confidence="high", effort="S", language="go",
                title=f"{f.get('osv')}: {o.get('summary','vulnerable dependency')[:140]}",
                description=(o.get("details", "") or o.get("summary", ""))[:800]
                + ("\n\nReachability: code path CALLED." if called
                   else "\n\nReachability: imported, not observed called."),
                recommendation="Upgrade module per the advisory's fixed version.",
                locations=[loc("go.mod")],
                snippet_key=f.get("osv", "")))
    return findings


def parse_clippy(text, repo):
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("reason") != "compiler-message":
            continue
        m = d.get("message", {})
        level = m.get("level")
        if level not in ("warning", "error"):
            continue
        code = (m.get("code") or {}).get("code", "rustc")
        spans = [s for s in m.get("spans", []) if s.get("is_primary")] or m.get("spans", [])
        if not spans:
            continue
        s = spans[0]
        yield new_finding(
            dimension="correctness", rule=f"clippy.{code}", source="clippy",
            severity="P2" if level == "error" else "P3",
            confidence="high", effort="XS", language="rust",
            title=f"{code}: {m.get('message','')[:140]}",
            description=m.get("rendered", m.get("message", ""))[:800],
            recommendation="See clippy lint docs.",
            locations=[loc(relpath(s.get("file_name", ""), repo), s.get("line_start"))],
            snippet_key=f"{code}@{s.get('line_start')}")


def parse_cargo_audit(data, repo):
    for v in (data.get("vulnerabilities", {}) or {}).get("list", []):
        adv = v.get("advisory", {})
        yield new_finding(
            dimension="security", rule=f"cargo-audit.{adv.get('id','RUSTSEC')}",
            source="cargo-audit", severity="P1", confidence="high", effort="S",
            language="rust",
            title=f"{adv.get('id')}: {adv.get('title','vulnerable crate')[:140]}",
            description=adv.get("description", "")[:800],
            recommendation=f"Upgrade {v.get('package',{}).get('name')} past the patched version.",
            locations=[loc("Cargo.lock")], snippet_key=adv.get("id", ""))


def parse_swiftlint(data, repo):
    for d in data:
        sev = "P2" if d.get("severity") == "error" else "P3"
        rule = d.get("rule_id", "swiftlint")
        yield new_finding(
            dimension="readability", rule=f"swiftlint.{rule}", source="swiftlint",
            severity=sev, confidence="high", effort="XS", language="swift",
            title=f"{rule}: {d.get('reason','')[:140]}",
            description=d.get("reason", ""),
            recommendation="Fix per SwiftLint rule docs.",
            locations=[loc(relpath(d.get("file", ""), repo), d.get("line"))],
            snippet_key=f"{rule}@{d.get('line')}")


def parse_cppcheck(text, repo):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return
    sev_map = {"error": "P1", "warning": "P2", "performance": "P2",
               "portability": "P3", "style": "P3", "information": "INFO"}
    dim_map = {"performance": "performance", "style": "readability"}
    for e in root.iter("error"):
        sev_word = e.get("severity", "style")
        locs = e.findall("location")
        if not locs:
            continue
        l0 = locs[0]
        yield new_finding(
            dimension=dim_map.get(sev_word, "correctness"),
            rule=f"cppcheck.{e.get('id')}", source="cppcheck",
            severity=sev_map.get(sev_word, "P3"),
            confidence="medium" if e.get("inconclusive") == "true" else "high",
            effort="S",
            title=f"{e.get('id')}: {e.get('msg','')[:140]}",
            description=e.get("verbose", e.get("msg", "")),
            recommendation="See cppcheck documentation for this check.",
            locations=[loc(relpath(l.get("file", ""), repo), int(l.get("line", 0)) or None)
                       for l in locs[:3]],
            snippet_key=f"{e.get('id')}@{l0.get('line')}")


def parse_gitleaks(data, repo):
    for d in data:
        yield new_finding(
            dimension="security", rule=f"gitleaks.{d.get('RuleID','secret')}",
            source="gitleaks", severity="P0", confidence="high", effort="S",
            title=f"Secret detected: {d.get('Description','')[:120]} in {d.get('File','')}",
            description=(f"Rule {d.get('RuleID')} matched in {d.get('File')} "
                         f"(commit {d.get('Commit','')[:8]}). Secret material is NOT "
                         f"reproduced here. Treat as compromised."),
            recommendation="Rotate the credential immediately; purge from history "
                           "(git filter-repo); add to secret manager + gitleaks baseline.",
            locations=[loc(d.get("File", ""), d.get("StartLine"))],
            snippet_key=d.get("Fingerprint", d.get("RuleID", "")))


def parse_osv(data, repo):
    for res in data.get("results", []) or []:
        src = (res.get("source", {}) or {}).get("path", "")
        for pkg in res.get("packages", []) or []:
            name = (pkg.get("package", {}) or {}).get("name", "?")
            for v in pkg.get("vulnerabilities", []) or []:
                sev = "P1"
                for s in v.get("severity", []) or []:
                    try:
                        if s.get("type") == "CVSS_V3" and float(str(s.get("score","0")).split("/")[0] if "/" not in str(s.get("score")) else 0) >= 9:
                            sev = "P0"
                    except (ValueError, TypeError):
                        pass
                yield new_finding(
                    dimension="security", rule=f"osv.{v.get('id','OSV')}",
                    source="osv-scanner", severity=sev, confidence="high", effort="S",
                    title=f"{v.get('id')}: {name} — {v.get('summary','vulnerable dependency')[:120]}",
                    description=(v.get("details", "") or v.get("summary", ""))[:800]
                    + "\n\nReachability not analyzed by this tool; verify before downgrading severity.",
                    recommendation=f"Upgrade {name} per advisory.",
                    locations=[loc(relpath(src, repo) or "lockfile")],
                    snippet_key=f"{v.get('id')}:{name}")


def parse_npm_audit(data, repo):
    sev_map = {"critical": "P0", "high": "P1", "moderate": "P2", "low": "P3"}
    for name, v in (data.get("vulnerabilities", {}) or {}).items():
        yield new_finding(
            dimension="security", rule=f"npm-audit.{name}", source="npm audit",
            severity=sev_map.get(v.get("severity"), "P2"), confidence="high",
            effort="S", language="javascript",
            title=f"Vulnerable dependency: {name} ({v.get('severity')})",
            description=f"{name}: {v.get('via') if isinstance(v.get('via'), str) else ''} "
                        f"range {v.get('range','')}. Direct: {v.get('isDirect')}.",
            recommendation="npm audit fix / targeted upgrade; verify breaking changes.",
            locations=[loc("package-lock.json")], snippet_key=name)


PARSERS = {
    "ruff.json": ("json", parse_ruff), "mypy.json": ("text", parse_mypy),
    "bandit.json": ("json", parse_bandit), "semgrep.json": ("json", parse_semgrep),
    "eslint.json": ("json", parse_eslint), "tsc.txt": ("text", parse_tsc),
    "madge.json": ("json", parse_madge), "gosec.json": ("json", parse_gosec),
    "staticcheck.json": ("text", parse_staticcheck), "govet.json": ("text", parse_govet),
    "govulncheck.json": ("text", parse_govulncheck), "clippy.json": ("text", parse_clippy),
    "cargo-audit.json": ("json", parse_cargo_audit),
    "swiftlint.json": ("json", parse_swiftlint), "cppcheck.xml": ("text", parse_cppcheck),
    "gitleaks.json": ("json", parse_gitleaks), "osv-scanner.json": ("json", parse_osv),
    "npm-audit.json": ("json", parse_npm_audit),
}

# readability/lint floods: cap per-rule, roll the remainder into one census finding
PER_RULE_CAP = 25


def cap_floods(findings):
    by_rule = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)
    out = []
    for rule, fs in by_rule.items():
        if len(fs) <= PER_RULE_CAP or fs[0]["severity"] in ("P0", "P1"):
            out.extend(fs)
            continue
        out.extend(fs[:PER_RULE_CAP])
        rest = fs[PER_RULE_CAP:]
        out.append(new_finding(
            dimension=fs[0]["dimension"], rule=f"{rule}.rollup-census",
            source=fs[0]["source"], severity=fs[0]["severity"], confidence="high",
            effort="M", language=fs[0].get("language"),
            title=f"{rule}: {len(fs)} total occurrences ({len(rest)} beyond the {PER_RULE_CAP} listed)",
            description=f"Census rollup. Top files: " + ", ".join(sorted(
                {x['locations'][0]['path'] for x in rest if x['locations']})[:10]),
            recommendation="Address via tooling config / autofix sweep rather than one-by-one.",
            locations=[], snippet_key=f"census:{rule}"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = Path(args.raw)
    profile = json.loads(Path(args.profile).read_text())
    repo = profile["repo"]

    all_findings, parsed, skipped = [], [], []
    for fname, (mode, fn) in PARSERS.items():
        p = raw / fname
        if not p.exists() or p.stat().st_size == 0:
            continue
        try:
            content = p.read_text(errors="ignore")
            data = json.loads(content) if mode == "json" else content
            got = list(fn(data, repo) or [])
            all_findings.extend(got)
            parsed.append((fname, len(got)))
        except Exception as e:
            skipped.append((fname, str(e)[:120]))

    all_findings = cap_floods(all_findings)
    out = Path(args.out)
    doc = load_findings(out / "findings.json")
    doc["audit"] = {"repo": repo, "commit": profile.get("commit"),
                    "scope": profile.get("scope", ".")}
    doc["findings"].extend(all_findings)
    save_findings(doc, out / "findings.json")
    final = json.loads((out / "findings.json").read_text())["findings"]
    print(f"parsed: " + ", ".join(f"{n} ({c})" for n, c in parsed))
    for n, err in skipped:
        print(f"PARSE FAILURE {n}: {err}")
    from fingerprint import severity_counts
    print("totals:", severity_counts(final, statuses=tuple(s for s in
          ("new", "persisting"))), f"-> {out/'findings.json'} ({len(final)} unique)")


if __name__ == "__main__":
    main()
