#!/usr/bin/env python3
"""Phase 2a: run available scanners; capture raw output to AUDIT_DIR/raw/.

Usage: run_scanners.py --profile P.json --tools T.json --out AUDIT_DIR
       [--offline] [--only security,...] [--timeout 600]

Scanners run inside the profile's `scope` (set by `detect_repo.py --path`), so a
sub-directory audit scans only that sub-directory. gitleaks is the exception: it
walks git history for the whole repository regardless of scope.

Read-only with respect to the repo (no test runs, no builds). Test/coverage/sanitizer
runs are deliberately excluded here — Claude requests those separately with user
approval per the language references. Tools that need a build (spotbugs, checkstyle,
cargo check, clippy pedantic) are never run here; they appear as coverage gaps.

staticcheck is skipped when golangci-lint is available, since golangci-lint bundles
it and the two would double-report under different rule names. gosec is still run
separately (golangci-lint does not enable it by default).

pip-licenses inventories the *current Python environment*, not necessarily the
repo's declared dependencies; the finding says so.

Writes raw/<tool>.<ext> and raw/_manifest.json (what ran, rc, duration, skips).
"""
import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

PURPOSE_DIM = [
    ("secret", "security"), ("sast", "security"),
    ("dep-vuln", "dependencies"), ("licens", "dependencies"), ("deps-policy", "dependencies"),
    ("lint", "readability"), ("format", "readability"), ("style", "readability"),
    ("types", "correctness"), ("static-analy", "correctness"), ("bug-pattern", "correctness"),
    ("vet", "correctness"), ("complexity", "maintainability"), ("duplication", "maintainability"),
    ("dead-", "maintainability"), ("import-cycles", "design"),
]

# tools that print their report on stderr
STDERR_TOOLS = {"cargo-deny", "swift-format"}

# tools that write a report file somewhere under raw/ that must be moved to raw/<tool>.<ext>
COLLECT = {"jscpd": ("jscpd/jscpd-report.json", "jscpd.json")}

JSCPD_IGNORE = "**/node_modules/**,**/.git/**,**/.audit/**,**/vendor/**,**/dist/**,**/build/**"


def purpose_dim(purpose):
    """Dimension a tool's registry purpose serves; None for infrastructure (git, runtimes)."""
    p = (purpose or "").lower()
    return next((d for k, d in PURPOSE_DIM if k in p), None)


def golangci_major():
    try:
        r = subprocess.run(["golangci-lint", "version"], capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    m = re.search(r"version\s+v?(\d+)", r.stdout + r.stderr)
    return int(m.group(1)) if m else None


def compile_commands_dir(repo):
    for d in (repo, repo / "build"):
        if (d / "compile_commands.json").exists():
            return d
    return None


def cmds_for(profile, tools, only, offline):
    """Returns (plan, skips). plan: (tool, dimension, argv, ext, cwd); ext None means
    the tool writes its own file. skips: tools available but not runnable here."""
    repo = (Path(profile["repo"]) / profile.get("scope", ".")).resolve()
    langs = {l["language"] for l in profile["languages"]}
    avail = {k for k, v in tools["tools"].items() if v["available"]}
    have_npx = shutil.which("npx") is not None
    have_pkg = (repo / "package.json").exists()

    def want(dim):
        return (not only) or (dim in only)

    out, skips = [], []
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
        if not offline:  # registry rulesets are fetched from the network
            A(("semgrep", "security",
               ["semgrep", "scan", *cfgs, "--json", "--quiet", "--timeout", "60"],
               "json", repo))
    if have_npx and want("maintainability"):
        A(("jscpd", "maintainability",
           ["npx", "--yes", "jscpd", ".", "--reporters", "json", "--output", "{RAW}/jscpd",
            "--silent", "--ignore", JSCPD_IGNORE], None, repo))

    if "python" in langs:
        if "ruff" in avail and want("readability"):
            A(("ruff", "readability", ["ruff", "check", "--output-format", "json",
                                       "--exit-zero", "."], "json", repo))
            A(("ruff-format", "readability", ["ruff", "format", "--check", "."], "txt", repo))
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
        if "pip-licenses" in avail and want("dependencies"):
            A(("pip-licenses", "dependencies", ["pip-licenses", "--format=json"], "json", repo))
        if "radon" in avail and want("maintainability"):
            A(("radon-cc", "maintainability", ["radon", "cc", "-j", "."], "json", repo))
            A(("radon-mi", "maintainability", ["radon", "mi", "-j", "."], "json", repo))
        if "vulture" in avail and want("maintainability"):
            A(("vulture", "maintainability",
               ["vulture", ".", "--min-confidence", "80",
                "--exclude", ".venv,venv,node_modules,.audit"], "txt", repo))

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
        if have_pkg and want("maintainability"):
            A(("knip", "maintainability",
               ["npx", "--yes", "knip", "--reporter", "json", "--no-exit-code"], "json", repo))
        if have_pkg and want("dependencies"):
            A(("license-checker", "dependencies",
               ["npx", "--yes", "license-checker", "--json"], "json", repo))
        pm_lock = [("package-lock.json", ["npm", "audit", "--json"]),
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
        golangci = "golangci-lint" in avail
        if golangci and want("correctness"):
            fmt = (["--output.json.path", "stdout"] if (golangci_major() or 1) >= 2
                   else ["--out-format", "json"])
            A(("golangci-lint", "correctness",
               ["golangci-lint", "run", *fmt, "./..."], "json", repo))
        if "staticcheck" in avail and not golangci and want("correctness"):
            A(("staticcheck", "correctness", ["staticcheck", "-f", "json", "./..."],
               "json", repo))
        if "gosec" in avail and want("security"):
            A(("gosec", "security", ["gosec", "-fmt", "json", "-quiet",
                                     "-no-fail", "./..."], "json", repo))
        if "govulncheck" in avail and not offline and want("dependencies"):
            A(("govulncheck", "dependencies", ["govulncheck", "-json", "./..."],
               "json", repo))
        if "go-licenses" in avail and not offline and want("dependencies"):
            A(("go-licenses", "dependencies", ["go-licenses", "report", "./..."], "csv", repo))

    if "rust" in langs and "cargo" in avail:
        if "cargo-clippy" in avail and want("correctness"):
            A(("clippy", "correctness", ["cargo", "clippy", "--all-targets",
                                         "--message-format=json"], "json", repo))
        if "cargo-audit" in avail and not offline and want("dependencies"):
            A(("cargo-audit", "dependencies", ["cargo", "audit", "--json"], "json", repo))
        if "cargo-deny" in avail and want("dependencies"):
            A(("cargo-deny", "dependencies", ["cargo", "deny", "--format", "json",
                                              "check"], "json", repo))

    if "swift" in langs:
        if "swiftlint" in avail and want("readability"):
            A(("swiftlint", "readability", ["swiftlint", "lint", "--reporter", "json",
                                            "--quiet"], "json", repo))
        if "swift-format" in avail and want("readability"):
            A(("swift-format", "readability", ["swift-format", "lint", "-r", "."], "txt", repo))

    if "c" in langs or "cpp" in langs:
        if "cppcheck" in avail and want("correctness"):
            A(("cppcheck", "correctness",
               ["cppcheck", "--enable=warning,style,performance,portability",
                "--inconclusive", "--xml", "--quiet", "."], "xml", repo))
        if "clang-tidy" in avail and want("correctness"):
            ccdir = compile_commands_dir(repo)
            if ccdir and shutil.which("run-clang-tidy"):
                A(("clang-tidy", "correctness",
                   ["run-clang-tidy", "-p", str(ccdir), "-quiet"], "txt", repo))
            else:
                skips.append({"tool": "clang-tidy", "dimension": "correctness",
                              "reason": "no compile_commands.json in scope or build/, "
                                        "or run-clang-tidy not on PATH"})

    if "java" in langs and "pmd" in avail and want("readability"):
        A(("pmd", "readability", ["pmd", "check", "-d", ".", "-R",
                                  "rulesets/java/quickstart.xml", "-f", "json",
                                  "--no-fail-on-violation"], "json", repo))

    if not offline and "osv-scanner" in avail and want("dependencies"):
        A(("osv-scanner", "dependencies",
           ["osv-scanner", "scan", "--format", "json", "-r", "."], "json", repo))
    return out, skips


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
    plan, manifest["skipped"] = cmds_for(profile, tools, only, args.offline)
    # coverage gaps: scanners that serve a wanted dimension but are not installed
    for name, t in tools["tools"].items():
        dim = purpose_dim(t.get("purpose"))
        if dim and not t["available"] and not t.get("via_npx") and (not only or dim in only):
            manifest["skipped"].append({"tool": name, "dimension": dim,
                                        "reason": "not installed", "purpose": t["purpose"]})
    for tool, dim, argv, ext, cwd in plan:
        argv = [a.replace("{RAW}", str(raw)) for a in argv]
        t0 = time.time()
        print(f"running {tool} ...", flush=True)
        try:
            r = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                               timeout=args.timeout)
            dest = raw / f"{tool}.{ext or 'json'}"
            if tool in COLLECT:
                src, name = COLLECT[tool]
                dest = raw / name
                if (raw / src).exists():
                    shutil.move(str(raw / src), str(dest))
                    shutil.rmtree(raw / src.split("/")[0], ignore_errors=True)
            elif ext is not None:
                dest.write_text(r.stderr if tool in STDERR_TOOLS else r.stdout)
            produced = dest.exists() and dest.stat().st_size > 0
            # many linters exit non-zero when they find something; only an exit
            # with no output means the scan itself failed
            if r.returncode != 0 and not produced:
                manifest["skipped"].append({
                    "tool": tool, "dimension": dim,
                    "reason": f"exit {r.returncode}: {(r.stderr or '').strip()[-200:] or 'no output'}"})
                continue
            manifest["ran"].append({"tool": tool, "dimension": dim, "rc": r.returncode,
                                    "seconds": round(time.time() - t0, 1),
                                    "argv": argv, "empty": not produced})
        except subprocess.TimeoutExpired:
            manifest["skipped"].append({"tool": tool, "dimension": dim,
                                        "reason": f"timeout {args.timeout}s"})
        except Exception as e:
            manifest["skipped"].append({"tool": tool, "dimension": dim, "reason": f"error: {e}"})
    (raw / "_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"ran {len(manifest['ran'])}, skipped {len(manifest['skipped'])}; "
          f"manifest at {raw/'_manifest.json'}")


if __name__ == "__main__":
    main()
