#!/usr/bin/env python3
"""Phase 2b: repo metrics — LOC, function sizes, complexity, churn, hotspots, censuses,
duplication, license inventory, coverage by area, import cycles.

Usage: metrics.py REPO --profile P.json --out AUDIT_DIR [--path SUBDIR]
Stdlib-only. --path defaults to the profile's scope.

Optional inputs read from AUDIT_DIR/raw/ when run_scanners produced them:
  radon-cc.json        real cyclomatic complexity for Python (else keyword proxy)
  jscpd.json           duplication report
  license-checker.json / pip-licenses.json / go-licenses.csv   license inventory
Coverage is read from the scope itself (coverage.xml, lcov.info, coverage.json).
Writes metrics.json.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
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
TODO_KW = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")

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

# ── function signature heuristics: (indent, name) per language ──────────────
_KW = {"if", "else", "for", "while", "switch", "catch", "return", "sizeof", "do",
       "function", "new", "throw", "case", "typedef", "using", "namespace"}
_MODS = r"(?:(?:public|private|protected|static|async|get|set|override|export|default)\s+)*"
FN_SIGS = {
    "python": [re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")],
    "go": [re.compile(r"^(\s*)func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(")],
    "rust": [re.compile(r"^(\s*)(?:pub(?:\([^)]*\))?\s+)?(?:(?:async|const|unsafe|extern\s+\"\w+\")\s+)*fn\s+(\w+)")],
    "swift": [re.compile(r"^(\s*)(?:[\w@]+\s+)*func\s+(\w+)")],
    "typescript": [
        re.compile(r"^(\s*)" + _MODS + r"function\s*\*?\s*(\w+)\s*[(<]"),
        re.compile(r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::\s*[^=]+)?=>"),
        re.compile(r"^(\s*)" + _MODS + r"(\w+)\s*\([^)]*\)\s*(?::\s*[^{;=]+)?\{\s*$"),
    ],
    "c": [re.compile(r"^( {0,4}|\t?)(?:[\w:<>\[\],~*&]+\s+)+\**(\w+)\s*\([^;]*\)\s*(?:const\s*)?(?:throws\s+[\w,\s.]+)?\s*\{?\s*$")],
}
FN_SIGS["javascript"] = FN_SIGS["typescript"]
FN_SIGS["cpp"] = FN_SIGS["java"] = FN_SIGS["c"]
INDENT_LANGS = {"python"}


def detect_sig(lang, line):
    for pat in FN_SIGS.get(lang, []):
        m = pat.match(line)
        if m and m.group(2) not in _KW:
            return len(m.group(1).expandtabs(4)), m.group(2)
    return None


def _indent(line):
    return len(line) - len(line.lstrip(" \t")) + line[:len(line) - len(line.lstrip())].count("\t") * 3


def function_spans(lang, lines):
    """Yield (name, start_line_1based, loc) for each detected function body."""
    n = len(lines)
    i = 0
    while i < n:
        sig = detect_sig(lang, lines[i])
        if not sig:
            i += 1
            continue
        indent, name = sig
        if lang in INDENT_LANGS:
            j = i + 1
            while j < n:
                s = lines[j].strip()
                if s and not s.startswith("#") and _indent(lines[j]) <= indent:
                    break
                j += 1
            end = j
        else:
            depth, opened, j = 0, False, i
            while j < n and j < i + 4 + (n if opened else 0):
                code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//.*$', "", lines[j])
                for ch in code:
                    if ch == "{":
                        depth += 1
                        opened = True
                    elif ch == "}":
                        depth -= 1
                if opened and depth <= 0:
                    break
                j += 1
            if not opened:
                i += 1
                continue
            end = min(j + 1, n)
        loc = sum(1 for l in lines[i:end] if l.strip())
        yield name, i + 1, loc
        i = max(i + 1, end if lang in INDENT_LANGS else i + 1)


def is_test(rel):
    low = rel.lower()
    return ("test" in low or "spec" in low or "__tests__" in low)


def analyze_file(p: Path, lang):
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        return None
    lines = text.splitlines()
    fns = list(function_spans(lang, lines))
    return {"loc": sum(1 for l in lines if l.strip()),
            "branches": len(BRANCH_KW.findall(text)),
            "todos": len(TODO_KW.findall(text)),
            "functions": fns, "lines": lines, "text": text}


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


def _load_json(p):
    try:
        return json.loads(Path(p).read_text()) if Path(p).exists() else None
    except (OSError, json.JSONDecodeError):
        return None


# ── optional raw inputs ──────────────────────────────────────────────────────
def radon_complexity(raw, repo, scope):
    """rel_path -> {"sum": N, "max": M} from radon cc -j (run with cwd=scope)."""
    data = _load_json(raw / "radon-cc.json")
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, blocks in data.items():
        if not isinstance(blocks, list):
            continue
        try:
            rel = str((scope / key).resolve().relative_to(repo))
        except ValueError:
            rel = key.lstrip("./")
        cc = [int(b.get("complexity", 0)) for b in blocks if isinstance(b, dict)]
        if cc:
            out[rel] = {"sum": sum(cc), "max": max(cc)}
    return out


def duplication(raw):
    data = _load_json(raw / "jscpd.json")
    if not isinstance(data, dict):
        return None
    total = (data.get("statistics") or {}).get("total") or {}
    dups = data.get("duplicates") or []

    def ref(f):
        f = f or {}
        return f"{f.get('name', '?')}:{f.get('start', '?')}-{f.get('end', '?')}"
    top = sorted(({"a": ref(d.get("firstFile")), "b": ref(d.get("secondFile")),
                   "lines": int(d.get("lines") or 0)} for d in dups),
                 key=lambda x: -x["lines"])[:10]
    return {"percentage": total.get("percentage"), "clones": len(dups), "top": top}


COPYLEFT = re.compile(r"\b(AGPL|GPL|SSPL|EUPL|OSL)\b", re.I)


def licenses(raw):
    pkgs = []  # (name, license)
    lc = _load_json(raw / "license-checker.json")
    if isinstance(lc, dict):
        for name, info in lc.items():
            lic = (info or {}).get("licenses")
            pkgs.append((name, ", ".join(lic) if isinstance(lic, list) else str(lic or "")))
    pl = _load_json(raw / "pip-licenses.json")
    if isinstance(pl, list):
        for row in pl:
            if isinstance(row, dict):
                pkgs.append((f"{row.get('Name', '?')}@{row.get('Version', '')}",
                             str(row.get("License") or "")))
    gl = raw / "go-licenses.csv"
    if gl.exists():
        try:
            for row in csv.reader(gl.read_text().splitlines()):
                if len(row) >= 3:
                    pkgs.append((row[0].strip(), row[2].strip()))
        except OSError:
            pass
    if not pkgs:
        return None
    by = Counter(lic or "UNKNOWN" for _, lic in pkgs)
    return {"packages": len(pkgs), "by_license": dict(by.most_common()),
            "copyleft": sorted(n for n, l in pkgs if COPYLEFT.search(l or "")),
            "unknown": sorted(n for n, l in pkgs if not l or l.upper() in ("UNKNOWN", "UNLICENSED"))}


# ── coverage by area ─────────────────────────────────────────────────────────
ROOT_DIRS = {"src", "lib", "app", "pkg", "internal", "cmd", "packages"}


def _area(path):
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
    if not parts or len(parts) == 1:
        return "(root)"
    if parts[0] in ROOT_DIRS and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0]


def _cov_cobertura(p):
    for cls in ET.parse(p).getroot().iter("class"):
        lines = list(cls.iter("line"))
        if lines:
            yield cls.get("filename", ""), len(lines), sum(1 for l in lines if int(l.get("hits", "0")) > 0)
        else:
            yield cls.get("filename", ""), 0, 0


def _cov_lcov(p):
    sf, lf, lh = None, 0, 0
    for ln in p.read_text(errors="ignore").splitlines():
        if ln.startswith("SF:"):
            sf, lf, lh = ln[3:].strip(), 0, 0
        elif ln.startswith("LF:"):
            lf = int(ln[3:])
        elif ln.startswith("LH:"):
            lh = int(ln[3:])
        elif ln.startswith("end_of_record") and sf:
            yield sf, lf, lh
            sf = None


def _cov_json(p):
    for path, info in (json.loads(p.read_text()).get("files") or {}).items():
        s = (info or {}).get("summary") or {}
        yield path, int(s.get("num_statements", 0)), int(s.get("covered_lines", 0))


def coverage(scope):
    candidates = [("coverage.xml", _cov_cobertura), ("coverage/coverage.xml", _cov_cobertura),
                  ("lcov.info", _cov_lcov), ("coverage/lcov.info", _cov_lcov),
                  ("coverage.json", _cov_json), ("coverage/coverage.json", _cov_json)]
    for name, parser in candidates:
        p = scope / name
        if not p.exists():
            continue
        try:
            recs = list(parser(p))
        except Exception:
            continue
        areas = defaultdict(lambda: [0, 0])
        for path, total, hit in recs:
            a = areas[_area(path)]
            a[0] += total
            a[1] += hit
        tl = sum(v[0] for v in areas.values())
        th = sum(v[1] for v in areas.values())
        by_area = {k: {"pct": round(100 * v[1] / v[0], 1) if v[0] else None, "lines": v[0]}
                   for k, v in sorted(areas.items())}
        return {"source": name, "overall": round(100 * th / tl, 1) if tl else None,
                "by_area": by_area,
                "uncovered_areas": sorted(k for k, v in by_area.items()
                                          if v["lines"] >= 100 and (v["pct"] or 0) < 30)}
    return None


# ── python import cycles ─────────────────────────────────────────────────────
IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import\s+([\w*, ()]+)|import\s+([\w., ]+))", re.M)


def python_import_cycles(py_files, scope):
    """py_files: {rel_to_scope: lines}. Returns list of cycles (module name lists)."""
    def split(rel):
        parts = rel[:-3].split("/")
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        # canonical = importable name: drop leading dirs that are not packages (src/ layouts)
        strip = 0
        while strip < len(parts) - 1 and not (scope / "/".join(parts[:strip + 1]) / "__init__.py").exists():
            strip += 1
        return parts, parts[strip:], is_pkg

    modules = {}  # dotted alias -> canonical
    for rel in py_files:
        parts, canon_parts, _ = split(rel)
        if not canon_parts:
            continue
        canon = ".".join(canon_parts)
        modules[canon] = canon
        for k in range(len(parts) - len(canon_parts) + 1):
            modules[".".join(parts[k:])] = canon

    def resolve(name):
        while name:
            if name in modules:
                return modules[name]
            name = name.rpartition(".")[0]
        return None

    graph = defaultdict(set)
    for rel, lines in py_files.items():
        _, canon_parts, is_pkg = split(rel)
        if not canon_parts:
            continue
        me = ".".join(canon_parts)
        pkg = canon_parts if is_pkg else canon_parts[:-1]
        for m in IMPORT_RE.finditer("\n".join(lines)):
            targets = []
            if m.group(1) is not None:
                base = m.group(1)
                if base.startswith("."):
                    up = len(base) - len(base.lstrip("."))
                    root = pkg[:len(pkg) - (up - 1)] if up > 1 else pkg
                    base = ".".join(root + ([base.lstrip(".")] if base.lstrip(".") else []))
                targets.append(base)
                for nm in m.group(2).replace("(", "").replace(")", "").split(","):
                    nm = nm.strip().split(" as ")[0].strip()
                    if nm and nm != "*":
                        targets.append(f"{base}.{nm}")
            else:
                for nm in m.group(3).split(","):
                    targets.append(nm.strip().split(" as ")[0].strip())
            for t in targets:
                r = resolve(t)
                if r and r != me:
                    graph[me].add(r)

    # Tarjan SCC
    index, low, on, stack, sccs, counter = {}, {}, set(), [], [], [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
    for v in list(graph):
        if v not in index:
            strong(v)
    return sorted(sccs, key=lambda c: (-len(c), c))[:20]


def _pct(sorted_vals, q):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1) + 0.5))]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--path", default=None, help="restrict scope to subdir (default: profile scope)")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    profile = _load_json(args.profile) or {}
    scope = (repo / (args.path or profile.get("scope") or ".")).resolve()
    out = Path(args.out)
    raw = out / "raw"

    radon = radon_complexity(raw, repo, scope)
    files, lang_loc, census = {}, Counter(), defaultdict(Counter)
    test_loc = src_loc = todo_count = 0
    all_fns, py_files, langs_seen = [], {}, set()
    for p in scope.rglob("*"):
        rel_parts = p.relative_to(repo).parts
        if any(part in SKIP_DIRS for part in rel_parts) or not p.is_file():
            continue
        lang = LANG_EXT.get(p.suffix.lower())
        if not lang:
            continue
        info = analyze_file(p, lang)
        if not info:
            continue
        rel = str(p.relative_to(repo))
        langs_seen.add(lang)
        lang_loc[lang] += info["loc"]
        todo_count += info["todos"]
        test = is_test(rel)
        if test:
            test_loc += info["loc"]
        else:
            src_loc += info["loc"]
        cx = radon.get(rel)
        complexity = cx["sum"] if cx else info["branches"]
        files[rel] = {"lang": lang, "loc": info["loc"], "branches": info["branches"],
                      "complexity": complexity,
                      "complexity_source": "radon" if cx else "keyword-proxy",
                      "branch_density": round(info["branches"] / max(info["loc"], 1), 3),
                      "max_fn_loc": max((f[2] for f in info["functions"]), default=0),
                      "is_test": test}
        if not test:
            all_fns += [(rel, name, line, loc) for name, line, loc in info["functions"]]
        if lang == "python":
            py_files[str(p.relative_to(scope))] = info["lines"]
        for name, pat in CENSUS_PATTERNS.get(lang, {}).items():
            n = len(re.findall(pat, info["text"]))
            if n:
                census[lang][name] += n

    churn = git_churn(repo)
    hotspots = []
    for rel, f in files.items():
        if f["is_test"] or f["loc"] < 30:
            continue
        score = f["complexity"] * (1 + churn.get(rel, 0))
        if score > 0:
            hotspots.append({"path": rel, "loc": f["loc"], "complexity": f["complexity"],
                             "branches": f["branches"], "commits_12mo": churn.get(rel, 0),
                             "score": score})
    hotspots.sort(key=lambda h: -h["score"])
    hotspots = hotspots[:25]
    for h in hotspots[:10]:
        h["authors"] = git_authors(repo, h["path"])

    big_files = sorted((dict(path=r, loc=f["loc"]) for r, f in files.items()
                        if not f["is_test"] and f["loc"] > 800),
                       key=lambda d: -d["loc"])[:20]

    fn_locs = sorted(f[3] for f in all_fns)
    functions = {
        "method": "heuristic",
        "count": len(fn_locs),
        "p50": _pct(fn_locs, 0.5), "p90": _pct(fn_locs, 0.9),
        "max": fn_locs[-1] if fn_locs else None,
        "over_80": [{"path": p, "name": n, "line": l, "loc": c}
                    for p, n, l, c in sorted(all_fns, key=lambda f: -f[3]) if c > 80][:20],
    }

    import_cycles = {}
    if "python" in langs_seen:
        import_cycles["python"] = python_import_cycles(py_files, scope)
    for lang in ("typescript", "javascript"):
        if lang in langs_seen:
            import_cycles[lang] = []
    if import_cycles and any(l in langs_seen for l in ("typescript", "javascript", "go", "rust")):
        import_cycles["note"] = ("TS/JS cycles come from raw/madge.json; Go and Rust reject "
                                 "import cycles at compile time (Rust: within a crate).")

    census_per_kloc = {
        lang: {k: round(v * 1000 / max(lang_loc[lang], 1), 2) for k, v in c.items()}
        for lang, c in census.items()}

    metrics = {
        "loc_by_language": dict(lang_loc),
        "source_loc": src_loc, "test_loc": test_loc,
        "test_to_source_ratio": round(test_loc / src_loc, 3) if src_loc else None,
        "file_count": len(files),
        "big_files": big_files,
        "functions": functions,
        "complexity_source": {l: ("radon" if l == "python" and radon else "keyword-proxy")
                              for l in sorted(langs_seen)},
        "hotspots": hotspots,
        "todo_fixme_count": todo_count,
        "census": {l: dict(c) for l, c in census.items()},
        "census_per_kloc": census_per_kloc,
        "duplication": duplication(raw),
        "licenses": licenses(raw),
        "coverage": coverage(scope),
        "import_cycles": import_cycles,
        "files": files,  # full table for dashboard treemap
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"LOC: {src_loc} src / {test_loc} test "
          f"(ratio {metrics['test_to_source_ratio']}); files: {len(files)}; "
          f"TODO/FIXME: {todo_count}; functions: {functions['count']} "
          f"(p50 {functions['p50']}, p90 {functions['p90']}, >80: {len(functions['over_80'])})")
    print("top hotspots:")
    for h in hotspots[:8]:
        print(f"  {h['score']:>7}  {h['path']}  (loc {h['loc']}, "
              f"commits {h['commits_12mo']})")
    print(f"wrote {out/'metrics.json'}")


if __name__ == "__main__":
    main()
