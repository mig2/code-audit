#!/usr/bin/env python3
"""Phase 0: detect languages, frameworks, build systems, sub-projects, service-ness.

Usage: detect_repo.py REPO --out AUDIT_DIR [--path SUBDIR]
Writes AUDIT_DIR/repo-profile.json
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

EXT_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".swift": "swift", ".go": "go", ".c": "c", ".h": "c-header",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".java": "java", ".rs": "rust", ".kt": "kotlin", ".rb": "ruby", ".php": "php",
}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", ".venv",
             "venv", "__pycache__", ".tox", ".mypy_cache", ".ruff_cache", "Pods",
             ".build", "DerivedData", ".next", ".audit", "coverage", ".idea",
             ".vscode", "site-packages", ".gradle", "out"}

MANIFESTS = {
    "pyproject.toml": "python", "setup.py": "python", "requirements.txt": "python",
    "Pipfile": "python", "package.json": "node", "tsconfig.json": "typescript",
    "go.mod": "go", "Cargo.toml": "rust", "pom.xml": "java", "build.gradle": "java",
    "build.gradle.kts": "java", "Package.swift": "swift", "Podfile": "swift",
    "CMakeLists.txt": "c-cpp", "Makefile": "c-cpp", "meson.build": "c-cpp",
    "configure.ac": "c-cpp",
}
SUBPROJECT_MANIFESTS = ["package.json", "pyproject.toml", "go.mod", "Cargo.toml",
                        "pom.xml", "build.gradle", "build.gradle.kts", "Package.swift"]

SERVICE_HINTS = [  # (filename-or-dep substring, where)
    "Dockerfile", "docker-compose", "Procfile", "k8s", "helm",
]
SERVICE_DEPS = ["fastapi", "flask", "django", "gunicorn", "uvicorn", "express",
                "fastify", "@nestjs", "koa", "gin-gonic", "labstack/echo", "go-chi",
                "axum", "actix-web", "warp", "tonic", "vapor", "hummingbird",
                "spring-boot", "vertx", "micronaut", "quarkus"]


def count_loc(path: Path):
    try:
        with open(path, "rb") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def detect(repo: Path, scope: Path):
    lang_loc, files_by_lang, manifests, test_loc, src_loc = {}, {}, [], 0, 0
    has_test_dir_hits = 0
    for p in scope.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(repo).parts):
            continue
        if p.is_file():
            rel = str(p.relative_to(repo))
            if p.name in MANIFESTS:
                manifests.append(rel)
            lang = EXT_LANG.get(p.suffix.lower())
            if lang:
                if lang == "c-header":
                    lang = "cpp" if (lang_loc.get("cpp", 0) >= lang_loc.get("c", 0)) else "c"
                loc = count_loc(p)
                lang_loc[lang] = lang_loc.get(lang, 0) + loc
                files_by_lang.setdefault(lang, 0)
                files_by_lang[lang] += 1
                low = rel.lower()
                if ("test" in low or "spec" in low or low.startswith("tests/")):
                    test_loc += loc
                    has_test_dir_hits += 1
                else:
                    src_loc += loc
    total = sum(lang_loc.values()) or 1
    languages = sorted(
        ({"language": k, "loc": v, "share": round(v / total, 3), "files": files_by_lang[k]}
         for k, v in lang_loc.items() if v > 0),
        key=lambda d: -d["loc"])
    # ts/js consolidation note
    return languages, manifests, test_loc, src_loc


def find_subprojects(repo: Path, scope: Path):
    """Nested manifests => sub-projects. Root-level manifest alone => single project."""
    subs = {}
    for p in scope.rglob("*"):
        if p.name in SUBPROJECT_MANIFESTS and p.is_file():
            rel_dir = p.parent.relative_to(repo)
            if any(part in SKIP_DIRS for part in rel_dir.parts):
                continue
            subs.setdefault(str(rel_dir) if str(rel_dir) != "." else ".", set()).add(p.name)
    if len(subs) <= 1:
        return []
    # nested under root: real monorepo signal only if non-root dirs have manifests
    nested = {d: sorted(m) for d, m in subs.items() if d != "."}
    if not nested:
        return []
    out = [{"name": Path(d).name, "path": d, "manifests": m} for d, m in sorted(nested.items())]
    if "." in subs:
        out.insert(0, {"name": "(root)", "path": ".", "manifests": sorted(subs["."])})
    return out


def read_text_safe(p: Path, limit=200_000):
    try:
        return p.read_text(errors="ignore")[:limit]
    except OSError:
        return ""


def detect_service(repo: Path, scope: Path, manifests):
    evidence = []
    for hint in SERVICE_HINTS:
        for hit in list(scope.glob(f"**/{hint}*"))[:3]:
            if not any(part in SKIP_DIRS for part in hit.relative_to(repo).parts):
                evidence.append(str(hit.relative_to(repo)))
    blob = ""
    for m in manifests:
        blob += read_text_safe(repo / m)
    for dep in SERVICE_DEPS:
        if dep in blob:
            evidence.append(f"dep:{dep}")
    return bool(evidence), sorted(set(evidence))[:10]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--out", required=True)
    ap.add_argument("--path", default=".", help="restrict scope to subdir")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    scope = (repo / args.path).resolve()
    if not scope.is_dir():
        sys.exit(f"scope not found: {scope}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    languages, manifests, test_loc, src_loc = detect(repo, scope)
    subprojects = find_subprojects(repo, scope)
    is_service, service_evidence = detect_service(repo, scope, manifests)

    remote = git(repo, "remote", "get-url", "origin")
    host = ("github" if "github" in remote else
            "gitlab" if "gitlab" in remote else
            ("unknown" if remote else None))
    profile = {
        "repo": str(repo),
        "scope": args.path,
        "commit": git(repo, "rev-parse", "HEAD") or None,
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD") or None,
        "remote": remote or None,
        "host": host,
        "languages": languages,
        "primary_language": languages[0]["language"] if languages else None,
        "manifests": manifests,
        "subprojects": subprojects,
        "is_monorepo": bool(subprojects),
        "is_service": is_service,
        "service_evidence": service_evidence,
        "loc": {"source": src_loc, "test": test_loc,
                "test_ratio": round(test_loc / src_loc, 3) if src_loc else None},
    }
    (out / "repo-profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    print(f"wrote {out/'repo-profile.json'}")
    print(f"languages: " + ", ".join(f"{l['language']} {l['share']:.0%}" for l in languages[:6]))
    if subprojects:
        print(f"monorepo: {len(subprojects)} sub-projects -> run per-project")
    print(f"service: {is_service}")


if __name__ == "__main__":
    main()
