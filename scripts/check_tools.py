#!/usr/bin/env python3
"""Phase 1: probe tool availability for detected languages.

Usage: check_tools.py --profile AUDIT_DIR/repo-profile.json --out AUDIT_DIR
Writes AUDIT_DIR/tool-report.json and prints a matrix.
"""
import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path

# tool registry: name -> (languages, purpose, version_cmd, install_strategy)
T = {
    "git":        (["*"], "vcs", ["git", "--version"], "system"),
    "gitleaks":   (["*"], "secrets", ["gitleaks", "version"], "binary:~/.local/bin"),
    "osv-scanner": (["*"], "dep-vulns", ["osv-scanner", "--version"], "binary:~/.local/bin"),
    "semgrep":    (["*"], "sast", ["semgrep", "--version"], "pipx install semgrep"),
    "scc":        (["*"], "loc-metrics", ["scc", "--version"], "binary:~/.local/bin (optional; metrics.py has fallback)"),
    "jscpd":      (["*"], "duplication", ["npx", "--yes", "jscpd", "--version"], "npx (auto)"),

    "ruff":       (["python"], "lint+format", ["ruff", "--version"], "pipx install ruff / uv tool install ruff"),
    "mypy":       (["python"], "types", ["mypy", "--version"], "pipx install mypy"),
    "bandit":     (["python"], "sast", ["bandit", "--version"], "pipx install bandit"),
    "pip-audit":  (["python"], "dep-vulns", ["pip-audit", "--version"], "pipx install pip-audit"),
    "radon":      (["python"], "complexity", ["radon", "--version"], "pipx install radon"),
    "vulture":    (["python"], "dead-code", ["vulture", "--version"], "pipx install vulture (optional)"),

    "node":       (["typescript", "javascript"], "runtime", ["node", "--version"], "nvm/volta (user-level)"),
    "eslint":     (["typescript", "javascript"], "lint", ["npx", "--yes", "eslint", "--version"], "npx (auto) / repo devDependency"),
    "tsc":        (["typescript"], "types", ["npx", "--yes", "tsc", "--version"], "npx (auto) / repo devDependency"),
    "madge":      (["typescript", "javascript"], "import-cycles", ["npx", "--yes", "madge", "--version"], "npx (auto)"),
    "knip":       (["typescript", "javascript"], "dead-exports", ["npx", "--yes", "knip", "--version"], "npx (auto, needs repo config tolerance)"),
    "license-checker": (["typescript", "javascript"], "licenses", ["npx", "--yes", "license-checker", "--version"], "npx (auto)"),

    "go":          (["go"], "toolchain (vet)", ["go", "version"], "tarball to ~/go or system"),
    "staticcheck": (["go"], "static-analysis", ["staticcheck", "-version"], "go install honnef.co/go/tools/cmd/staticcheck@latest"),
    "gosec":       (["go"], "sast", ["gosec", "-version"], "go install github.com/securego/gosec/v2/cmd/gosec@latest"),
    "govulncheck": (["go"], "dep-vulns(reachability)", ["govulncheck", "-version"], "go install golang.org/x/vuln/cmd/govulncheck@latest"),
    "golangci-lint": (["go"], "lint-meta", ["golangci-lint", "--version"], "binary installer to ~/go/bin"),
    "go-licenses": (["go"], "licenses", ["go-licenses", "help"], "go install github.com/google/go-licenses@latest"),

    "cargo":       (["rust"], "toolchain", ["cargo", "--version"], "rustup (user-level)"),
    "cargo-clippy": (["rust"], "lint", ["cargo", "clippy", "--version"], "rustup component add clippy"),
    "cargo-audit": (["rust"], "dep-vulns", ["cargo", "audit", "--version"], "cargo install cargo-audit"),
    "cargo-deny":  (["rust"], "deps-policy+licenses", ["cargo", "deny", "--version"], "cargo install cargo-deny"),

    "swiftlint":   (["swift"], "lint", ["swiftlint", "version"], "brew install swiftlint / release binary to ~/.local/bin"),
    "swift":       (["swift"], "toolchain", ["swift", "--version"], "swift.org toolchain (user-level ok)"),
    "swift-format": (["swift"], "format", ["swift-format", "--version"], "brew / swift toolchain bundled"),
    "xcodebuild":  (["swift"], "static-analyze (macOS only)", ["xcodebuild", "-version"], "Xcode (macOS only)"),

    "cppcheck":    (["c", "cpp"], "static-analysis", ["cppcheck", "--version"], "distro pkg or build to ~/.local (root may be needed)"),
    "clang-tidy":  (["c", "cpp"], "static-analysis", ["clang-tidy", "--version"], "distro pkg / llvm release tarball to ~/.local"),

    "java":        (["java"], "runtime", ["java", "-version"], "sdkman (user-level)"),
    "pmd":         (["java"], "lint", ["pmd", "--version"], "release zip to ~/.local/share/code-audit/tools"),
    "spotbugs":    (["java"], "bug-patterns (needs build)", ["spotbugs", "-version"], "release zip to ~/.local/share/code-audit/tools"),
    "checkstyle":  (["java"], "style", ["checkstyle", "--version"], "release jar to ~/.local/share/code-audit/tools"),

    "gh":          (["*"], "issue filing (GitHub)", ["gh", "--version"], "release binary to ~/.local/bin"),
    "glab":        (["*"], "issue filing (GitLab)", ["glab", "--version"], "release binary to ~/.local/bin"),
}

NPX_TOOLS = {"eslint", "tsc", "madge", "knip", "license-checker", "jscpd"}


def probe(cmd):
    exe = cmd[0]
    if exe != "npx" and shutil.which(exe) is None:
        return False, None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (r.stdout or r.stderr).strip().splitlines()
        ok = r.returncode == 0 or (exe == "java")  # java -version exits 0 but prints to stderr
        return ok, (out[0][:80] if out else None)
    except Exception:
        return False, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fast", action="store_true", help="skip npx probes (slow on cold cache)")
    args = ap.parse_args()
    profile = json.loads(Path(args.profile).read_text())
    langs = {l["language"] for l in profile["languages"]}
    if "javascript" in langs or "typescript" in langs:
        langs.add("javascript"); langs.add("typescript")

    report = {"platform": platform.system().lower(), "tools": {}}
    for name, (tl, purpose, cmd, install) in T.items():
        relevant = "*" in tl or any(l in langs for l in tl)
        if not relevant:
            continue
        if args.fast and cmd[0] == "npx":
            avail, ver = (shutil.which("npx") is not None), "via npx (unprobed)"
        else:
            avail, ver = probe(cmd)
        report["tools"][name] = {
            "available": avail, "version": ver, "purpose": purpose,
            "languages": tl, "install": install,
            "via_npx": name in NPX_TOOLS,
        }
    # platform notes
    notes = []
    if "swift" in langs and report["platform"] != "darwin":
        notes.append("Linux: xcodebuild analyze unavailable; Swift coverage degrades "
                     "to SwiftLint + compiler diagnostics (SwiftPM only) + manual review.")
    report["notes"] = notes

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tool-report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"{'TOOL':<16}{'STATUS':<12}{'PURPOSE':<28}INSTALL (if missing)")
    for name, t in sorted(report["tools"].items(), key=lambda kv: (not kv[1]["available"], kv[0])):
        status = "ok" if t["available"] else "MISSING"
        print(f"{name:<16}{status:<12}{t['purpose']:<28}{'' if t['available'] else t['install']}")
    for n in notes:
        print(f"note: {n}")
    print(f"wrote {out/'tool-report.json'}")


if __name__ == "__main__":
    main()
