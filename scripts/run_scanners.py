#!/usr/bin/env python3
"""Phase 2a: run available scanners; capture raw output to AUDIT_DIR/raw/.

Usage: run_scanners.py --profile P.json --tools T.json --out AUDIT_DIR
       [--offline] [--only security,...] [--project NAME] [--timeout 600]

Read-only with respect to the repo (no test runs, no builds). Test/coverage/sanitizer
runs are deliberately excluded here — Claude requests those separately with user
approval per the language references.
Writes raw/<tool>.<ext> and raw/_manifest.json (what ran, rc, duration, skips).
"""
import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

NETWORK_TOOLS = {"pip-audit", "osv-scanner", "cargo-audit", "npm-audit", "govulncheck"}


def cmds_for(profile, tools, only, offline):
    repo = Path(profile["repo"])
    langs = {l["language"] for l in profile["languages"]}
    avail = {k for k, v in tools["tools"].items() if v["available"]}
    have_npx = shutil.which("npx") is not None

    def want(dim):
        return (not only) or (dim in only)

    out = []  # (tool, dimension, argv, ext, cwd)
    A = out.append
    if "gitleaks" in avail and want("security"):
        A(("gitleaks", "security",
           ["gitleaks", "detect", "--source", str(repo), "--no-banner",
            "--report-format", "json", "--report-path", "{RAW}/gitleaks.json",
            "--exit-code", "0"], None, repo))
    if "semgrep" in avail and want("security"):
        cfgs = []
        for l, c in [("python", "p/python"), ("typescript", "p/typescript"),
                     ("javascript", "p/javascript"), ("go", "p/golang"),
                     ("java", "p/java"), ("c", "p/c"), ("cpp", "p/cpp")]:
            if l in langs:
                cfgs += ["--config", c]
        cfgs += ["--config", "p/security-audit"]
        if offline:
            cfgs = ["--config", "auto"]  # still networky; effectively skip below
        if not offline:
            A(("semgrep", "security",
               ["semgrep", "scan", *cfgs, "--json", "--quiet", "--timeout", "60"],
               "json", repo))

    if "python" in langs:
        if "ruff" in avail and want("readability"):
            A(("ruff", "readability", ["ruff", "check", "--output-format", "json",
                                       "--exit-zero", "."], "json", repo))
        if "mypy" in avail and want("correctness"):
            A(("mypy", "correctness", ["mypy", "--output", "json",
                                       "--ignore-missing-imports", "."], "json", repo))
        if "bandit" in avail and want("security"):
            A(("bandit", "security", ["bandit", "-r", ".", "-f", "json",
                                      "-x", "./tests,./test,./.venv,./venv",
                                      "--exit-zero"], "json", repo))
        if "pip-audit" in avail and not offline and want("dependencies"):
            req = repo / "requirements.txt"
            argv = ["pip-audit", "-f", "json"]
            if req.exists():
                argv += ["-r", str(req), "--disable-pip"]
            A(("pip-audit", "dependencies", argv, "json", repo))
        if "radon" in avail and want("maintainability"):
            A(("radon-cc", "maintainability", ["radon", "cc", "-j", "."], "json", repo))

    if ("typescript" in langs or "javascript" in langs) and have_npx:
        if want("readability"):
            A(("eslint", "readability", ["npx", "--yes", "eslint", ".", "-f", "json"],
               "json", repo))
        if "typescript" in langs and (repo / "tsconfig.json").exists() and want("correctness"):
            A(("tsc", "correctness", ["npx", "--yes", "tsc", "--noEmit",
                                      "--pretty", "false"], "txt", repo))
        if want("design"):
            A(("madge", "design", ["npx", "--yes", "madge", "--circular",
                                   "--json", "."], "json", repo))
        pm_lock = [( "package-lock.json", ["npm", "audit", "--json"]),
                   ("pnpm-lock.yaml", ["pnpm", "audit", "--json"]),
                   ("yarn.lock", ["yarn", "audit", "--json"])]
        if not offline and want("dependencies"):
            for lock, argv in pm_lock:
                if (repo / lock).exists() and shutil.which(argv[0]):
                    A(("npm-audit", "dependencies", argv, "json", repo))
                    break

    if "go" in langs and "go" in avail:
        if want("correctness"):
            A(("govet", "correctness", ["go", "vet", "-json", "./..."], "json", repo))
        if "staticcheck" in avail and want("correctness"):
            A(("staticcheck", "correctness", ["staticcheck", "-f", "json", "./..."],
               "json", repo))
        if "gosec" in avail and want("security"):
            A(("gosec", "security", ["gosec", "-fmt", "json", "-quiet",
                                     "-no-fail", "./..."], "json", repo))
        if "govulncheck" in avail and not offline and want("dependencies"):
            A(("govulncheck", "dependencies", ["govulncheck", "-json", "./..."],
               "json", repo))

    if "rust" in langs and "cargo" in avail:
        if "cargo-clippy" in avail and want("correctness"):
            A(("clippy", "correctness", ["cargo", "clippy", "--all-targets",
                                         "--message-format=json"], "json", repo))
        if "cargo-audit" in avail and not offline and want("dependencies"):
            A(("cargo-audit", "dependencies", ["cargo", "audit", "--json"], "json", repo))
        if "cargo-deny" in avail and want("dependencies"):
            A(("cargo-deny", "dependencies", ["cargo", "deny", "--format", "json",
                                              "check"], "json", repo))

    if "swift" in langs and "swiftlint" in avail and want("readability"):
        A(("swiftlint", "readability", ["swiftlint", "lint", "--reporter", "json",
                                        "--quiet"], "json", repo))

    if ("c" in langs or "cpp" in langs) and "cppcheck" in avail and want("correctness"):
        A(("cppcheck", "correctness",
           ["cppcheck", "--enable=warning,style,performance,portability",
            "--inconclusive", "--xml", "--quiet", "."], "xml", repo))

    if "java" in langs and "pmd" in avail and want("readability"):
        A(("pmd", "readability", ["pmd", "check", "-d", ".", "-R",
                                  "rulesets/java/quickstart.xml", "-f", "json",
                                  "--no-fail-on-violation"], "json", repo))

    if not offline and "osv-scanner" in avail and want("dependencies"):
        A(("osv-scanner", "dependencies",
           ["osv-scanner", "scan", "--format", "json", "-r", "."], "json", repo))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--tools", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    profile = json.loads(Path(args.profile).read_text())
    tools = json.loads(Path(args.tools).read_text())
    only = set(filter(None, args.only.split(",")))
    raw = Path(args.out) / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    manifest = {"ran": [], "skipped": []}
    plan = cmds_for(profile, tools, only, args.offline)
    # record skips: tools relevant but unavailable
    for name, t in tools["tools"].items():
        if not t["available"] and not t.get("via_npx"):
            manifest["skipped"].append({"tool": name, "reason": "not installed",
                                        "purpose": t["purpose"]})
    for tool, dim, argv, ext, cwd in plan:
        argv = [a.replace("{RAW}", str(raw)) for a in argv]
        t0 = time.time()
        print(f"running {tool} ...", flush=True)
        try:
            r = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                               timeout=args.timeout)
            dest = raw / f"{tool}.{ext or 'json'}"
            if ext is not None:  # tool writes to stdout
                dest.write_text(r.stdout if r.stdout.strip() else r.stderr)
            manifest["ran"].append({"tool": tool, "dimension": dim, "rc": r.returncode,
                                    "seconds": round(time.time() - t0, 1),
                                    "argv": argv})
        except subprocess.TimeoutExpired:
            manifest["skipped"].append({"tool": tool, "reason": f"timeout {args.timeout}s"})
        except Exception as e:
            manifest["skipped"].append({"tool": tool, "reason": f"error: {e}"})
    (raw / "_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"ran {len(manifest['ran'])}, skipped {len(manifest['skipped'])}; "
          f"manifest at {raw/'_manifest.json'}")


if __name__ == "__main__":
    main()
