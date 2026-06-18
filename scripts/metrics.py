#!/usr/bin/env python3
"""Phase 2b: repo metrics — LOC, sizes, complexity proxy, churn, hotspots, censuses.

Usage: metrics.py REPO --profile P.json --out AUDIT_DIR
Stdlib-only; complexity is a branch-keyword proxy (consistent, comparable, fast),
refined by radon/clippy etc. where those ran.
Writes metrics.json.
"""
import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", ".venv",
             "venv", "__pycache__", "Pods", ".build", ".next", ".audit", "coverage",
             "DerivedData", ".tox", "out", ".gradle"}
LANG_EXT = {".py": "python", ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
            ".cjs": "javascript", ".swift": "swift", ".go": "go", ".c": "c",
            ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
            ".java": "java", ".rs": "rust"}

BRANCH_KW = re.compile(
    r"\b(if|else if|elif|for|while|case|when|catch|except|&&|\|\||guard|select)\b")

CENSUS_PATTERNS = {  # language -> {census_name: regex}
    "python": {
        "type_ignore": r"#\s*type:\s*ignore", "noqa": r"#\s*noqa",
        "bare_except": r"except\s*:", "eval_exec": r"\b(eval|exec)\s*\(",
        "any_annotation": r":\s*Any\b|\bAny\]",
    },
    "typescript": {
        "any": r":\s*any\b|as\s+any\b", "ts_ignore": r"@ts-(ignore|expect-error)",
        "non_null_assert": r"\w!\.", "eval": r"\beval\s*\(",
    },
    "javascript": {"eval": r"\beval\s*\(", "var_decl": r"\bvar\s+\w"},
    "swift": {
        "force_unwrap": r"\w!(?![=!])", "try_bang": r"\btry!\s",
        "force_cast": r"\bas!\s", "iuo_decl": r":\s*\w+!",
        "unchecked_sendable": r"@unchecked\s+Sendable",
    },
    "go": {
        "any_param": r"\binterface\{\}|\bany\b", "panic": r"\bpanic\(",
        "err_discard": r"\b_\s*=\s*\w+\.?\w*\(|,\s*_\s*:?=",
        "nolint": r"//nolint",
    },
    "rust": {
        "unsafe_block": r"\bunsafe\s*\{", "unwrap": r"\.unwrap\(\)",
        "expect": r"\.expect\(", "transmute": r"\btransmute\b",
        "allow_attr": r"#\[allow\(",
    },
    "java": {
        "suppress_unchecked": r'@SuppressWarnings\("unchecked"\)',
        "raw_exception_catch": r"catch\s*\(\s*(Exception|Throwable)\b",
        "system_out": r"System\.out\.print",
    },
    "c": {"unsafe_str": r"\b(strcpy|strcat|sprintf|gets)\s*\(",
          "goto": r"\bgoto\s+\w"},
    "cpp": {"raw_new": r"\bnew\s+\w", "c_cast": r"=\s*\(\s*\w+\s*\*?\s*\)\s*\w",
            "unsafe_str": r"\b(strcpy|strcat|sprintf)\s*\("},
}


def is_test(rel):
    low = rel.lower()
    return ("test" in low or "spec" in low or "__tests__" in low)


def analyze_file(p: Path):
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        return None
    lines = text.splitlines()
    loc = sum(1 for l in lines if l.strip())
    branches = len(BRANCH_KW.findall(text))
    # longest function proxy: max gap between def-like lines (rough; refined by radon etc.)
    return {"loc": loc, "branches": branches, "text": text}


def git_churn(repo, months=12):
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={months} months ago",
             "--name-only", "--pretty=format:"],
            capture_output=True, text=True, timeout=120)
        return Counter(l.strip() for l in r.stdout.splitlines() if l.strip())
    except Exception:
        return Counter()


def git_authors(repo, path):
    try:
        r = subprocess.run(["git", "-C", str(repo), "shortlog", "-sn", "--", path],
                           capture_output=True, text=True, timeout=60)
        return len(r.stdout.strip().splitlines())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--path", default=".")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    scope = (repo / args.path).resolve()

    files, lang_loc, census = {}, Counter(), defaultdict(Counter)
    test_loc = src_loc = 0
    for p in scope.rglob("*"):
        rel_parts = p.relative_to(repo).parts
        if any(part in SKIP_DIRS for part in rel_parts) or not p.is_file():
            continue
        lang = LANG_EXT.get(p.suffix.lower())
        if not lang:
            continue
        info = analyze_file(p)
        if not info:
            continue
        rel = str(p.relative_to(repo))
        lang_loc[lang] += info["loc"]
        if is_test(rel):
            test_loc += info["loc"]
        else:
            src_loc += info["loc"]
        density = info["branches"] / max(info["loc"], 1)
        files[rel] = {"lang": lang, "loc": info["loc"], "branches": info["branches"],
                      "branch_density": round(density, 3), "is_test": is_test(rel)}
        for name, pat in CENSUS_PATTERNS.get(lang, {}).items():
            n = len(re.findall(pat, info["text"]))
            if n:
                census[lang][name] += n

    churn = git_churn(repo)
    # hotspots: complexity proxy × churn, source files only
    hotspots = []
    for rel, f in files.items():
        if f["is_test"] or f["loc"] < 30:
            continue
        score = f["branches"] * (1 + churn.get(rel, 0))
        if score > 0:
            hotspots.append({"path": rel, "loc": f["loc"], "branches": f["branches"],
                             "commits_12mo": churn.get(rel, 0), "score": score})
    hotspots.sort(key=lambda h: -h["score"])
    hotspots = hotspots[:25]
    for h in hotspots[:10]:
        h["authors"] = git_authors(repo, h["path"])

    big_files = sorted((dict(path=r, loc=f["loc"]) for r, f in files.items()
                        if not f["is_test"] and f["loc"] > 800),
                       key=lambda d: -d["loc"])[:20]
    todo = Counter()
    for rel, f in files.items():
        pass  # counted below to avoid re-read; cheap enough to redo:
    todo_count = 0
    for p in scope.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(repo).parts):
            continue
        if p.suffix.lower() in LANG_EXT and p.is_file():
            try:
                todo_count += len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b",
                                             p.read_text(errors="ignore")))
            except OSError:
                pass

    census_per_kloc = {
        lang: {k: round(v * 1000 / max(lang_loc[lang], 1), 2) for k, v in c.items()}
        for lang, c in census.items()}

    metrics = {
        "loc_by_language": dict(lang_loc),
        "source_loc": src_loc, "test_loc": test_loc,
        "test_to_source_ratio": round(test_loc / src_loc, 3) if src_loc else None,
        "file_count": len(files),
        "big_files": big_files,
        "hotspots": hotspots,
        "todo_fixme_count": todo_count,
        "census": {l: dict(c) for l, c in census.items()},
        "census_per_kloc": census_per_kloc,
        "files": files,  # full table for dashboard treemap
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"LOC: {src_loc} src / {test_loc} test "
          f"(ratio {metrics['test_to_source_ratio']}); files: {len(files)}; "
          f"TODO/FIXME: {todo_count}")
    print("top hotspots:")
    for h in hotspots[:8]:
        print(f"  {h['score']:>7}  {h['path']}  (loc {h['loc']}, "
              f"commits {h['commits_12mo']})")
    print(f"wrote {out/'metrics.json'}")


if __name__ == "__main__":
    main()
