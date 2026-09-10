#!/usr/bin/env python3
"""Phase 6: file findings as tracker issues. ALWAYS run --dry-run first.

Usage: file_issues.py AUDIT_DIR --host github|gitlab --repo OWNER/NAME
       [--dry-run] [--close-fixed] [--rollup-threshold 4] [--no-rollup]
       [--project NAME] [--force-repo]

Hierarchy: root audit issue -> dimension parents -> finding issues (+ rollups).
Idempotent: consults issues-manifest.json and searches issue bodies for
<!-- ca-fp:... --> markers. persisting -> comment; fixed -> comment (+close).
Requires authenticated gh / glab.
"""
import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fingerprint import SEV_ORDER, DIMENSIONS  # noqa: E402

MARK = "<!-- ca-fp:{} -->"


def sh(argv, check=True, inp=None):
    r = subprocess.run(argv, capture_output=True, text=True, input=inp, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:4])}… failed: {r.stderr.strip()[:300]}")
    return r.stdout


class GitHub:
    def __init__(self, repo):
        self.repo = repo

    def existing_markers(self):
        out = sh(["gh", "issue", "list", "--repo", self.repo, "--state", "all",
                  "--search", "ca-fp in:body", "--limit", "500",
                  "--json", "number,title,body,state,url"], check=False)
        found = {}
        try:
            for it in json.loads(out or "[]"):
                for line in (it.get("body") or "").splitlines():
                    if "ca-fp:" in line:
                        fp = line.split("ca-fp:", 1)[1].split("-->")[0].strip()
                        found[fp] = it
        except json.JSONDecodeError:
            pass
        return found

    def labels(self):
        out = sh(["gh", "label", "list", "--repo", self.repo, "--limit", "200",
                  "--json", "name"], check=False)
        try:
            return {l["name"] for l in json.loads(out or "[]")}
        except json.JSONDecodeError:
            return set()

    def create_label(self, name, color="6b7f8c"):
        sh(["gh", "label", "create", name, "--repo", self.repo, "--color", color,
            "--force"], check=False)

    def create(self, title, body, labels):
        argv = ["gh", "issue", "create", "--repo", self.repo, "--title", title,
                "--body", body]
        for l in labels:
            argv += ["--label", l]
        url = sh(argv).strip()
        return url, int(url.rstrip("/").rsplit("/", 1)[-1])

    def comment(self, number, body):
        sh(["gh", "issue", "comment", str(number), "--repo", self.repo,
            "--body", body])

    def close(self, number, comment):
        sh(["gh", "issue", "close", str(number), "--repo", self.repo,
            "--comment", comment], check=False)

    def link_subissue(self, parent, child):
        """Native sub-issues via GraphQL; returns False on failure (caller falls back)."""
        q = """query($owner:String!,$name:String!,$n:Int!){
          repository(owner:$owner,name:$name){issue(number:$n){id}}}"""
        owner, name = self.repo.split("/")
        try:
            pid = json.loads(sh(["gh", "api", "graphql", "-f", f"query={q}",
                                 "-F", f"owner={owner}", "-F", f"name={name}",
                                 "-F", f"n={parent}"]))["data"]["repository"]["issue"]["id"]
            cid = json.loads(sh(["gh", "api", "graphql", "-f", f"query={q}",
                                 "-F", f"owner={owner}", "-F", f"name={name}",
                                 "-F", f"n={child}"]))["data"]["repository"]["issue"]["id"]
            m = """mutation($p:ID!,$c:ID!){
              addSubIssue(input:{issueId:$p,subIssueId:$c}){issue{number}}}"""
            sh(["gh", "api", "graphql", "-f", f"query={m}",
                "-F", f"p={pid}", "-F", f"c={cid}"])
            return True
        except Exception:
            return False


class GitLab:
    def __init__(self, repo):
        self.repo = repo

    def existing_markers(self):
        out = sh(["glab", "issue", "list", "--repo", self.repo, "--all",
                  "--search", "ca-fp", "--output", "json", "--per-page", "100"],
                 check=False)
        found = {}
        try:
            for it in json.loads(out or "[]"):
                body = it.get("description") or ""
                for line in body.splitlines():
                    if "ca-fp:" in line:
                        fp = line.split("ca-fp:", 1)[1].split("-->")[0].strip()
                        found[fp] = {"number": it["iid"], "url": it["web_url"],
                                     "state": it["state"], "title": it["title"]}
        except json.JSONDecodeError:
            pass
        return found

    def labels(self):
        out = sh(["glab", "label", "list", "--repo", self.repo, "--output", "json",
                  "--per-page", "100"], check=False)
        try:
            return {l["name"] for l in json.loads(out or "[]")}
        except json.JSONDecodeError:
            return set()

    def create_label(self, name, color="#6b7f8c"):
        sh(["glab", "label", "create", "--repo", self.repo, "--name", name,
            "--color", color], check=False)

    def create(self, title, body, labels):
        argv = ["glab", "issue", "create", "--repo", self.repo, "--title", title,
                "--description", body, "--yes"]
        if labels:
            argv += ["--label", ",".join(labels)]
        out = sh(argv)
        url = next((l for l in out.splitlines() if "://" in l), "").strip()
        num = int(url.rstrip("/").rsplit("/", 1)[-1]) if url else None
        return url, num

    def comment(self, number, body):
        sh(["glab", "issue", "note", str(number), "--repo", self.repo,
            "--message", body])

    def close(self, number, comment):
        self.comment(number, comment)
        sh(["glab", "issue", "close", str(number), "--repo", self.repo], check=False)

    def link_subissue(self, parent, child):
        sh(["glab", "issue", "link", str(parent), str(child),
            "--repo", self.repo], check=False)
        return True


# ───────────────────────────── plan construction ────────────────────────────
def finding_body(f, profile, project):
    commit = profile.get("commit") or ""
    remote = (profile.get("remote") or "").removesuffix(".git")
    lines = [f"**Dimension:** {f['dimension']} · **Severity:** {f['severity']} · "
             f"**Confidence:** {f['confidence']} · **Effort:** {f['effort']}",
             ""]
    for l in f["locations"][:6]:
        ln = f":{l['startLine']}" if l.get("startLine") else ""
        if remote and "github" in remote and commit:
            ref = f"{remote}/blob/{commit}/{l['path']}"
            ref += f"#L{l['startLine']}" if l.get("startLine") else ""
            lines.append(f"- [`{l['path']}{ln}`]({ref})")
        else:
            lines.append(f"- `{l['path']}{ln}`")
    lines += ["", f['description'][:2500], ""]
    if f.get("recommendation"):
        lines += ["**Recommendation:**", f["recommendation"][:1200], ""]
    lines += [f"_code-audit {date.today().isoformat()}"
              + (f" · project {project}" if project else "") + "_",
              MARK.format(f["fingerprint"])]
    return "\n".join(lines)


def build_plan(findings, args, profile, project):
    open_f = [f for f in findings
              if f["status"] in ("new", "persisting") and f["severity"] != "INFO"]
    fixed_f = [f for f in findings if f["status"] == "fixed"]
    rollups, singles = {}, []
    if not args.no_rollup:
        eligible = {}
        for f in open_f:
            if f["severity"] in ("P2", "P3") and f["effort"] in ("XS", "S"):
                eligible.setdefault(f["dimension"], []).append(f)
        for dim, fs in eligible.items():
            if len(fs) >= args.rollup_threshold:
                rollups[dim] = fs
    rolled = {f["fingerprint"] for fs in rollups.values() for f in fs}
    singles = [f for f in open_f if f["fingerprint"] not in rolled]
    return singles, rollups, fixed_f


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audit_dir")
    ap.add_argument("--host", choices=["github", "gitlab"], required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--close-fixed", action="store_true")
    ap.add_argument("--rollup-threshold", type=int, default=4)
    ap.add_argument("--no-rollup", action="store_true")
    ap.add_argument("--project", default=None, help="monorepo project name for titles")
    ap.add_argument("--force-repo", action="store_true")
    args = ap.parse_args()
    d = Path(args.audit_dir)
    doc = json.loads((d / "findings.json").read_text())
    profile = json.loads((d / "repo-profile.json").read_text()) if (d / "repo-profile.json").exists() else {}

    remote = profile.get("remote") or ""
    if not args.force_repo and remote and args.repo.lower() not in remote.lower():
        sys.exit(f"--repo {args.repo} does not match remote {remote}; "
                 f"use --force-repo if intentional")

    cli = GitHub(args.repo) if args.host == "github" else GitLab(args.repo)
    proj = args.project
    ns = f"{proj}/" if proj else ""
    singles, rollups, fixed_f = build_plan(doc["findings"], args, profile, proj)

    manifest_p = d / "issues-manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {"issues": {}}

    # label plan
    want = {"audit"} | {f"audit:{f['dimension']}" for f in singles}
    want |= {f"audit:{dim}" for dim in rollups} | ({"audit:rollup"} if rollups else set())
    want |= {f["severity"] for f in singles}
    existing = set() if args.dry_run else cli.labels()
    to_create = sorted(want - existing) if not args.dry_run else sorted(want)

    # ── dry-run plan ──
    print(f"=== ISSUE PLAN ({args.host} {args.repo}"
          + (f", project {proj}" if proj else "") + ") ===")
    print(f"root: [Audit] {Path(profile.get('repo','repo')).name} — "
          f"{date.today().isoformat()}")
    dims = sorted({f["dimension"] for f in singles} | set(rollups),
                  key=lambda x: DIMENSIONS.index(x) if x in DIMENSIONS else 99)
    for dim in dims:
        fs = sorted([f for f in singles if f["dimension"] == dim],
                    key=lambda f: SEV_ORDER[f["severity"]])
        print(f"├── [Audit/{ns}{dim.capitalize()}]")
        for f in fs:
            mark = "persisting→comment" if f["status"] == "persisting" and \
                manifest["issues"].get(f["fingerprint"]) else "create"
            print(f"│   ├── [{f['severity']}] {f['title'][:80]}  ({mark})")
        if dim in rollups:
            print(f"│   └── rollup: {len(rollups[dim])} small fixes (P2/P3 × XS/S)")
    if fixed_f:
        print(f"fixed since baseline: {len(fixed_f)} → comment"
              + (" + close" if args.close_fixed else " (no close; use --close-fixed)"))
    print(f"labels to ensure: {', '.join(to_create) or '(all exist)'}")
    n_create = len(singles) + len(rollups) + len(dims) + 1
    print(f"creations: ~{n_create} issues")
    if args.dry_run:
        print("\nDRY RUN — nothing filed. Confirm this plan, then rerun without --dry-run.")
        return

    # ── live run ──
    markers = cli.existing_markers()
    for name in to_create:
        cli.create_label(name)

    audit_fp = f"audit-root:{date.today().isoformat()}:{ns}"
    root_title = f"[Audit{('/'+proj) if proj else ''}] " \
                 f"{Path(profile.get('repo','repo')).name} — {date.today().isoformat()}"
    root_body = (f"Audit root. Dimensions and findings are linked below.\n\n"
                 + MARK.format(audit_fp))
    root_url, root_num = cli.create(root_title, root_body, ["audit"])
    print(f"root: {root_url}")
    task_lines = []

    for dim in dims:
        cat_title = f"[Audit/{ns}{dim.capitalize()}]"
        cat_body = f"Findings for **{dim}**.\n\n" + MARK.format(f"audit-cat:{ns}{dim}")
        cat_url, cat_num = cli.create(cat_title, cat_body, ["audit", f"audit:{dim}"])
        if not cli.link_subissue(root_num, cat_num):
            task_lines.append(f"- [ ] {cat_url}")
        child_lines = []
        for f in sorted([x for x in singles if x["dimension"] == dim],
                        key=lambda x: SEV_ORDER[x["severity"]]):
            fp = f["fingerprint"]
            known = manifest["issues"].get(fp) or markers.get(fp)
            if known:
                num = known.get("number") or known.get("num")
                cli.comment(num, f"Still present in {date.today().isoformat()} audit.")
                print(f"  comment: #{num} {f['title'][:60]}")
                continue
            title = f"[{f['severity']}] {f['title'][:120]}"
            url, num = cli.create(title, finding_body(f, profile, proj),
                                  ["audit", f"audit:{dim}", f["severity"]])
            manifest["issues"][fp] = {"number": num, "url": url}
            manifest_p.write_text(json.dumps(manifest, indent=2))
            f["tracker"] = {"url": url, "id": str(num)}
            if not cli.link_subissue(cat_num, num):
                child_lines.append(f"- [ ] {url}")
            print(f"  filed: {url}")
        if dim in rollups:
            fs = rollups[dim]
            lines = [f"Rollup of {len(fs)} small fixes (P2/P3, effort XS/S):", ""]
            for f in fs:
                l0 = f["locations"][0]["path"] if f["locations"] else ""
                lines.append(f"- [ ] `{l0}` — {f['title'][:90]} "
                             + MARK.format(f["fingerprint"]))
            lines += ["", MARK.format(f"audit-rollup:{ns}{dim}")]
            url, num = cli.create(f"[Audit/{ns}{dim.capitalize()}] rollup: "
                                  f"{len(fs)} small fixes", "\n".join(lines),
                                  ["audit", f"audit:{dim}", "audit:rollup"])
            cli.link_subissue(cat_num, num) or child_lines.append(f"- [ ] {url}")
            print(f"  rollup: {url}")
        if child_lines:
            cli.comment(cat_num, "Tracked findings:\n" + "\n".join(child_lines))
    if task_lines:
        cli.comment(root_num, "Categories:\n" + "\n".join(task_lines))

    for f in fixed_f:
        known = manifest["issues"].get(f["fingerprint"]) or markers.get(f["fingerprint"])
        if known:
            num = known.get("number")
            msg = f"Not detected in {date.today().isoformat()} audit — likely fixed."
            cli.close(num, msg) if args.close_fixed else cli.comment(num, msg)

    (d / "findings.json").write_text(json.dumps(doc, indent=2) + "\n")
    manifest_p.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {manifest_p}")


if __name__ == "__main__":
    main()
