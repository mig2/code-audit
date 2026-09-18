#!/usr/bin/env python3
"""Calibration signals: deterministic inputs for the proportionality / ownership review.

Usage: calibration_signals.py REPO --audit AUDIT_DIR [--out DIR]
Reads AUDIT_DIR/{repo-profile,metrics,findings}.json (all optional) and walks the repo
scope. Writes calibration-signals.json. Every regex-derived block carries
"method": "heuristic"; blocks with no inputs are null.
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "audit" / "scripts"))
from metrics import SKIP_DIRS, LANG_EXT, is_test  # noqa: E402

CAP = 20
MANIFESTS = ("requirements.txt", "requirements-dev.txt", "requirements_dev.txt",
             "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "package.json", "go.mod",
             "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "Package.swift")
LOCK_OR_MANIFEST = {"package.json", "package-lock.json", "pyproject.toml", "Cargo.toml",
                    "Cargo.lock", "poetry.lock", "pnpm-lock.yaml", "yarn.lock", "go.sum",
                    "uv.lock", "Pipfile.lock", "composer.lock", "composer.json",
                    "Package.resolved"}

IFACE_RE = {
    "python": re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)\s*:", re.M),
    "typescript": re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:interface|abstract\s+class)\s+(\w+)", re.M),
    "go": re.compile(r"^\s*type\s+(\w+)\s+interface\s*\{", re.M),
    "java": re.compile(r"^\s*(?:public\s+|private\s+|protected\s+)?(?:static\s+)?(?:abstract\s+class|interface)\s+(\w+)", re.M),
    "rust": re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)", re.M),
    "swift": re.compile(r"^\s*(?:public\s+|internal\s+)?protocol\s+(\w+)", re.M),
}
IFACE_RE["javascript"] = IFACE_RE["typescript"]
IMPL_RE = {
    "typescript": re.compile(r"\b(?:implements|extends)\s+([\w<>, ]+?)\s*(?:\{|implements)"),
    "java": re.compile(r"\b(?:implements|extends)\s+([\w<>, ]+?)\s*(?:\{|implements)"),
    "rust": re.compile(r"\bimpl(?:<[^>]*>)?\s+(\w+)(?:<[^>]*>)?\s+for\s+"),
    "go": re.compile(r"^\s*var\s+_\s+(\w+)\s*=", re.M),
    "swift": re.compile(r"^\s*(?:final\s+)?(?:class|struct|enum|extension)\s+\w+\s*:\s*([\w, ]+)", re.M),
}
IMPL_RE["javascript"] = IMPL_RE["typescript"]
PATTERN_NAME = re.compile(r"(Factory|Manager|Provider|Handler|Service|Abstract|Base|Impl|Strategy|Adapter|Facade|Registry|Orchestrator)")
DI_FRAMEWORKS = ("dependency-injector", "dependency_injector", "tsyringe", "inversify", "dagger",
                 "guice", "google/wire", "go.uber.org/fx", "injector", "punq", "lagom")
GENERIC_RE = re.compile(r"<T\b|\bTypeVar\(|\bGeneric\[")

ENV_RE = re.compile(r"os\.environ|\bgetenv\(|process\.env|os\.Getenv|std::env::var|System\.getenv|ENV\[")
CLI_FLAG_RE = re.compile(r"add_argument\(|#\[arg|\.Flags\(\)|\.option\(|\.flag\(|\.PersistentFlags\(\)")
FEATURE_FLAG_RE = re.compile(r"\b(?:FLAG_\w+|FEATURE_\w+|ENABLE_\w+|\w+_ENABLED)\b")

TRY_RE = re.compile(r"^\s*try\s*[:{]", re.M)
BROAD_CATCH_RE = re.compile(r"except\s*:|except\s+(?:Exception|BaseException)\b|catch\s*\(\s*(?:Exception|Throwable|RuntimeException)\b")
EMPTY_CATCH_RE = re.compile(r"except[^\n]*:\s*\n\s*pass\b|catch\s*(?:\([^)]*\))?\s*\{\s*\}")
UNWRAP_RE = re.compile(r"\.unwrap\(\)|\.expect\(")
PANIC_RE = re.compile(r"\bpanic\(|\bpanic!\(|\bunreachable!\(|\bfatalError\(|\bos\.Exit\(")
ERR_DISCARD_RE = re.compile(r",\s*_\s*:?=|^\s*_\s*=\s*\w", re.M)
CUSTOM_EXC_RE = re.compile(r"class\s+\w+\s*\(\s*[\w.]*(?:Exception|Error)\s*\)|class\s+\w+\s+extends\s+[\w.]*(?:Error|Exception)\b|impl\s+(?:std::error::)?Error\s+for|#\[derive\([^)]*\bError\b")
# Boundary detection runs on code with string/comment content stripped, so the names below
# must be identifiers or decorators, not strings. The two Node hooks are matched on the
# call form instead because their event names are string arguments.
BOUNDARY_RE = re.compile(r"sys\.excepthook\s*=|\(err,\s*req,\s*res,\s*next\)|\brecover\(\)|@ControllerAdvice|@ExceptionHandler|set_exception_handler\(|\bErrorBoundary\b|catch_unwind\(|app\.exception_handler\(|@app\.errorhandler\(|add_exception_handler\(")
BOUNDARY_CALL_RE = re.compile(r"process\.on\(\s*['\"](?:uncaughtException|unhandledRejection)['\"]")
COMMENT_RE = re.compile(r"//.*$|#.*$|/\*.*?\*/")
STRING_RE = re.compile(r"`(?:\\.|[^`\\])*`|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")
# TS/JS interface bodies: a method signature or a function-typed property marks it behavioral
TS_METHOD_RE = re.compile(r"^\s*(?:readonly\s+)?\w+\??\s*(?:<[^>]*>)?\s*\([^)]*\)\s*:|^\s*(?:readonly\s+)?\w+\??\s*:\s*\([^)]*\)\s*=>", re.M)
LOG_RE = re.compile(r"\b(?:log|logger|logging|LOG|_log|slog|zap|logrus|winston|pino|tracing)\b\s*[.:]+\s*(?:debug|info|warn|warning|error|exception|critical|fatal|Debug|Info|Warn|Error|Fatal)\s*[!(]|console\.(?:warn|error)\(")
PRINT_RE = re.compile(r"(?<![.\w])print\(|console\.log\(|fmt\.Print(?:ln|f)?\(|println!\(|System\.out\.print|\bdbg!\(|\bpp\(|\bvar_dump\(")

ASSERT_RE = re.compile(r"\bassert\b|\.assert\w*\(|\bexpect\(|\bt\.(?:Error|Fatal|Fail)\w*\(|\bassert(?:_eq|_ne)?!\(|\bXCTAssert\w*\(|\bassert(?:That|Equals|True|False|NotNull|Null|Raises|Throws)\w*\(|\bshould\b|\bmust\.")
MOCK_RE = re.compile(r"\bmock\.|(?<![.\w])patch\(|(?<![.\w])patch\.object\(|jest\.mock\(|jest\.fn\(|\bsinon\.|gomock\.|Mockito\.|@Mock\b|\bmockito\b|\bMagicMock\(|\bAsyncMock\(|vi\.mock\(|vi\.fn\(|\bmockall\b|\bmocket\b")
PRIVATE_ACCESS_RE = re.compile(r"\._[A-Za-z]\w*\b|\b__\w+\b(?!__)")
ARRANGE_RE = re.compile(r"(?:#|//)\s*Arrange\b")
ASSERT_MARK_RE = re.compile(r"(?:#|//)\s*Assert\b")
SNAPSHOT_RE = re.compile(r"toMatchSnapshot|toMatchInlineSnapshot|assert_snapshot|insta::|\.snap\b|snapshot\(")
TEST_FN_RE = {
    "python": re.compile(r"^\s*(?:async\s+)?def\s+test_\w+", re.M),
    "typescript": re.compile(r"^\s*(?:it|test)(?:\.each\([^)]*\))?\s*\(", re.M),
    "go": re.compile(r"^func\s+Test\w+", re.M),
    "rust": re.compile(r"^\s*#\[(?:tokio::)?test\]", re.M),
    "java": re.compile(r"^\s*@Test\b", re.M),
    "swift": re.compile(r"^\s*func\s+test\w+", re.M),
}
TEST_FN_RE["javascript"] = TEST_FN_RE["typescript"]
CRITICAL_RE = re.compile(r"money|price|billing|payment|auth|crypto|pars|date|time|token|permission", re.I)

DUP_PAIRS = [("requests", "httpx"), ("requests", "aiohttp"), ("moment", "dayjs"),
             ("moment", "date-fns"), ("lodash", "underscore"), ("lodash", "ramda"),
             ("axios", "node-fetch"), ("axios", "got"), ("jest", "vitest"), ("mocha", "jest"),
             ("pytest", "unittest2"), ("pyyaml", "ruamel.yaml"), ("click", "typer"),
             ("express", "fastify"), ("flask", "fastapi"), ("black", "ruff"),
             ("eslint", "biome"), ("prettier", "biome")]
FRAMEWORKS = ("django", "flask", "fastapi", "express", "fastify", "nestjs", "@nestjs/core",
              "spring-boot", "spring-boot-starter", "rails", "gin-gonic", "echo", "actix-web",
              "axum", "rocket", "koa", "hapi")
DATA_STORES = ("sqlalchemy", "django.db", "prisma", "typeorm", "knex", "sequelize", "gorm",
               "sqlx", "diesel", "hibernate", "jpa", "mongoose", "redis", "psycopg", "pymongo",
               "asyncpg", "pg", "mysql", "sqlite", "boto3", "dynamodb", "mongodb")
HTTP_LIBS = ("requests", "httpx", "aiohttp", "axios", "node-fetch", "got", "undici", "reqwest",
             "okhttp", "retrofit", "alamofire", "urllib3")
CONCURRENCY_RE = re.compile(r"\bthreading\.|\basyncio\.|\bgo\s+func\b|\bchan\b|\bsync\.(?:Mutex|RWMutex|WaitGroup)|\bMutex<|\bRwLock<|tokio::spawn|Promise\.all\(|worker_threads|\bmultiprocessing\.|concurrent\.futures|\bDispatchQueue\b|\bactor\b|ExecutorService|CompletableFuture|\bselect\s*\{")
SECURITY_RE = re.compile(r"\bauth\w*|\bjwt\b|\boauth\b|\bsession\b|\bpassword\b|\bcrypto\b|\bhmac\b|\bbcrypt\b|\bargon2?\b|\bsql\b|cursor\.execute\(|\bexec\(|\bsubprocess\.|child_process|os\.system\(|\bshell=True", re.I)
HTTP_CALL_RE = re.compile(r"\bfetch\(|\brequests\.(?:get|post|put|delete|patch|request)\(|\bhttp\.(?:Get|Post|NewRequest)\(|\baxios\.|\bhttpx\.|reqwest::|urlopen\(")
HARD_SPOT_RE = re.compile(r"\bDecimal\b|\bdecimal\b|\bmoney\b|\bcurrency\b|\btimezone\b|\btzinfo\b|\bzoneinfo\b|\bDST\b|\bparser\b|\bgrammar\b|\btokenizer\b|re\.compile\(|Regex::new\(|\bBigDecimal\b|\bbigint\b")
USERS_RE = re.compile(r"\bproduction\b|\bcustomers?\b|\busers?\b|\bSLA\b|\buptime\b", re.I)
DEPLOY_FILES = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
                "compose.yaml", "Procfile", "serverless.yml", "serverless.yaml", "fly.toml",
                "render.yaml", "app.yaml", "vercel.json", "netlify.toml")
DEPLOY_DIRS = ("k8s", "kubernetes", "helm", "charts", "terraform", "infra", "deploy", ".github/workflows")
INSTRUCTION_FILES = ("CLAUDE.md", ".cursorrules", ".cursor", "AGENTS.md",
                     ".github/copilot-instructions.md", ".windsurfrules", "GEMINI.md",
                     ".clinerules", ".aider.conf.yml")
GENERATED_RE = re.compile(r"generated by|auto-?generated|do not edit|@generated", re.I)
AI_COAUTHOR_RE = re.compile(r"Claude|Copilot|ChatGPT|Cursor|Codex|Gemini|Generated with|Co-Authored-By:.*(?:noreply@anthropic|github-copilot)", re.I)
CONVENTIONAL_RE = re.compile(r"^(?:feat|fix|chore|docs|refactor|test|build|ci|perf|style|revert)(?:\([^)]*\))?!?:")

COMMENT_LINE = {"python": re.compile(r"^\s*#"), "default": re.compile(r"^\s*(?://|/\*|\*)")}
PY_DEF_RE = re.compile(r"^(\s*)def\s+([A-Za-z]\w*)\s*\(.*\)\s*(?:->[^:]+)?:\s*$", re.M)
TS_EXPORT_FN_RE = re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\s+\w+", re.M)


def _load(p):
    try:
        return json.loads(Path(p).read_text()) if Path(p).exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _read(p):
    try:
        return p.read_text(errors="ignore")
    except OSError:
        return ""


def _ratio(a, b, nd=3):
    return round(a / b, nd) if b else None


def walk(repo, scope):
    files = []
    for p in sorted(scope.rglob("*")):
        try:
            rel_parts = p.relative_to(repo).parts
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel_parts) or not p.is_file():
            continue
        lang = LANG_EXT.get(p.suffix.lower())
        if not lang:
            continue
        rel = "/".join(rel_parts)
        files.append({"path": p, "rel": rel, "lang": lang, "text": _read(p), "is_test": is_test(rel)})
    return files


def read_manifests(scope):
    out = {}
    for name in MANIFESTS:
        p = scope / name
        if p.exists():
            out[name] = _read(p)
    for p in sorted(scope.glob("requirements*.txt")):
        out.setdefault(p.name, _read(p))
    return out


# ── blocks ───────────────────────────────────────────────────────────────────
def size_block(profile, metrics, files):
    src = [f for f in files if not f["is_test"]]
    return {
        "source_loc": (metrics or {}).get("source_loc") or sum(
            sum(1 for l in f["text"].splitlines() if l.strip()) for f in src),
        "test_loc": (metrics or {}).get("test_loc") or sum(
            sum(1 for l in f["text"].splitlines() if l.strip()) for f in files if f["is_test"]),
        "file_count": len(files),
        "languages": [l["language"] for l in (profile or {}).get("languages", [])] or sorted({f["lang"] for f in files}),
        "is_service": (profile or {}).get("is_service"),
        "primary_language": (profile or {}).get("primary_language"),
    }


def _brace_body(text, start):
    """Text of the {...} block that begins at or after `start`; '' if none."""
    i = text.find("{", start)
    if i < 0:
        return ""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return text[i + 1:]


def indirection_block(files, manifests, source_loc):
    ifaces = {}  # name -> file
    impls = Counter()
    abc_names = set()
    type_shapes = 0
    implemented = set()
    for f in files:
        if f["is_test"]:
            continue
        if f["lang"] in ("typescript", "javascript"):
            for m in IMPL_RE["typescript"].finditer(f["text"]):
                implemented.update(re.split(r"[,\s]+", re.sub(r"<[^>]*>", "", m.group(1))))
    for f in files:
        if f["is_test"]:
            continue
        lang, text = f["lang"], f["text"]
        pat = IFACE_RE.get(lang)
        if not pat:
            continue
        if lang == "python":
            classes = [(m.group(1), m.group(2), m.start()) for m in pat.finditer(text)]
            for i, (name, bases, start) in enumerate(classes):
                end = classes[i + 1][2] if i + 1 < len(classes) else len(text)
                body = text[start:end]
                if re.search(r"\b(?:ABC|ABCMeta|Protocol)\b", bases) or "@abstractmethod" in body:
                    ifaces.setdefault(name, f["rel"])
                    abc_names.add(name)
        elif lang in ("typescript", "javascript"):
            # `interface Foo { a: string }` is a data shape, not an abstraction; only bodies
            # with a method signature, abstract classes, or anything something `implements`
            # count as behavioral interfaces
            for m in pat.finditer(text):
                name = m.group(1)
                behavioral = ("abstract" in m.group(0) or name in implemented
                              or bool(TS_METHOD_RE.search(_brace_body(text, m.end()))))
                if behavioral:
                    ifaces.setdefault(name, f["rel"])
                else:
                    type_shapes += 1
        else:
            for m in pat.finditer(text):
                ifaces.setdefault(m.group(1), f["rel"])
    for f in files:
        if f["is_test"]:
            continue
        lang, text = f["lang"], f["text"]
        if lang == "python":
            for m in IFACE_RE["python"].finditer(text):
                for base in re.split(r"[,\s]+", m.group(2)):
                    base = base.split(".")[-1].split("[")[0]
                    if base in abc_names and m.group(1) not in abc_names:
                        impls[base] += 1
            continue
        pat = IMPL_RE.get(lang)
        if not pat:
            continue
        for m in pat.finditer(text):
            for name in re.split(r"[,\s]+", re.sub(r"<[^>]*>", "", m.group(1))):
                if name in ifaces:
                    impls[name] += 1
    single = sorted(({"name": n, "file": fp, "implementations": impls.get(n, 0)}
                     for n, fp in ifaces.items() if impls.get(n, 0) <= 1),
                    key=lambda x: (x["implementations"], x["name"]))
    pattern_files = sorted({f["rel"] for f in files if not f["is_test"] and PATTERN_NAME.search(Path(f["rel"]).stem)})
    blob = "\n".join(manifests.values()).lower()
    di = sorted({d for d in DI_FRAMEWORKS if d in blob})
    generics = sum(len(GENERIC_RE.findall(f["text"])) for f in files if not f["is_test"])
    depth = max((len(Path(f["rel"]).parts) - 1 for f in files), default=0)
    return {
        "method": "heuristic",
        "interfaces": len(ifaces),
        "type_shapes": type_shapes,
        "implementations": sum(impls.values()),
        "single_impl_interfaces": single[:CAP],
        "pattern_named_files": {"count": len(pattern_files), "top": pattern_files[:CAP]},
        "di_frameworks": di,
        "generic_params": generics,
        "max_dir_depth": depth,
        "layers_per_kloc": _ratio(len(ifaces) + len(pattern_files), source_loc / 1000, 2) if source_loc else None,
    }


def _top_level_keys(p):
    text = _read(p)
    try:
        if p.suffix == ".json":
            d = json.loads(text)
            return len(d) if isinstance(d, dict) else None
        if p.suffix == ".toml":
            import tomllib
            return len(tomllib.loads(text))
        if p.suffix in (".yaml", ".yml"):
            return len(re.findall(r"^[A-Za-z_][\w.-]*\s*:", text, re.M))
        if p.suffix == ".ini":
            return len(re.findall(r"^\[", text, re.M))
    except Exception:
        return None
    return None


def config_block(files, scope):
    src = [f for f in files if not f["is_test"]]
    cfgs = []
    for d in (scope, scope / "config", scope / "conf", scope / "settings"):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if (p.is_file() and p.suffix in (".yaml", ".yml", ".toml", ".ini", ".json")
                    and p.name not in LOCK_OR_MANIFEST and not p.name.startswith("tsconfig")):
                cfgs.append({"file": str(p.relative_to(scope)), "keys": _top_level_keys(p)})
    flags = set()
    for f in src:
        flags.update(FEATURE_FLAG_RE.findall(f["text"]))
    return {
        "method": "heuristic",
        "env_reads": sum(len(ENV_RE.findall(f["text"])) for f in src),
        "config_files": cfgs[:CAP],
        "cli_flags": sum(len(CLI_FLAG_RE.findall(f["text"])) for f in src),
        "feature_flags": {"count": len(flags), "top": sorted(flags)[:CAP]},
    }


def error_block(files, metrics):
    src = [f for f in files if not f["is_test"]]
    census = (metrics or {}).get("census") or {}
    boundary = []
    for f in src:
        for i, line in enumerate(f["text"].splitlines(), 1):
            code = COMMENT_RE.sub("", line)
            if BOUNDARY_CALL_RE.search(code) or BOUNDARY_RE.search(STRING_RE.sub("", code)):
                boundary.append(f"{f['rel']}:{i}")
                if len(boundary) >= 5:
                    break
        if len(boundary) >= 5:
            break
    unwraps = sum(len(UNWRAP_RE.findall(f["text"])) for f in src if f["lang"] == "rust")
    unwraps += (census.get("swift") or {}).get("force_unwrap", 0)
    go_census = (census.get("go") or {}).get("err_discard")
    err_discards = go_census if go_census is not None else sum(
        len(ERR_DISCARD_RE.findall(f["text"])) for f in src if f["lang"] == "go")
    return {
        "method": "heuristic",
        "try_blocks": sum(len(TRY_RE.findall(f["text"])) for f in src),
        "broad_catches": sum(len(BROAD_CATCH_RE.findall(f["text"])) for f in src),
        "empty_catches": sum(len(EMPTY_CATCH_RE.findall(f["text"])) for f in src),
        "unwraps": unwraps,
        "panics": sum(len(PANIC_RE.findall(f["text"])) for f in src),
        "err_discards": err_discards,
        "custom_exception_types": sum(len(CUSTOM_EXC_RE.findall(f["text"])) for f in src),
        "error_boundary": bool(boundary),
        "error_boundary_evidence": boundary,
        "logging_calls": sum(len(LOG_RE.findall(f["text"])) for f in src),
        "print_debugging": sum(len(PRINT_RE.findall(f["text"])) for f in src),
    }


def _test_stem(rel):
    stem = Path(rel).name
    for suf in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".swift", ".kt"):
        if stem.endswith(suf):
            stem = stem[:-len(suf)]
            break
    for pre in ("test_",):
        if stem.startswith(pre):
            stem = stem[len(pre):]
    for suf in ("_test", ".test", ".spec", "_spec", "Tests", "Test", "Spec"):
        if stem.endswith(suf) and len(stem) > len(suf):
            stem = stem[:-len(suf)]
            break
    return stem.lower()


def testing_block(files, metrics):
    tests = [f for f in files if f["is_test"]]
    src = [f for f in files if not f["is_test"]]
    src_stems = {Path(f["rel"]).stem.lower(): f["rel"] for f in src}
    mirrored, no_assert, private, boiler, snaps, asserts, mocks = 0, 0, 0, 0, 0, 0, 0
    mirrored_src = set()
    for f in tests:
        text = f["text"]
        asserts += len(ASSERT_RE.findall(text))
        mocks += len(MOCK_RE.findall(text))
        private += len(PRIVATE_ACCESS_RE.findall(text))
        snaps += len(SNAPSHOT_RE.findall(text))
        if ARRANGE_RE.search(text) and ASSERT_MARK_RE.search(text):
            boiler += 1
        stem = _test_stem(f["rel"])
        if stem in src_stems:
            mirrored += 1
            mirrored_src.add(stem)
        pat = TEST_FN_RE.get(f["lang"])
        if pat:
            starts = [m.start() for m in pat.finditer(text)]
            for i, s in enumerate(starts):
                body = text[s:starts[i + 1] if i + 1 < len(starts) else len(text)]
                if not ASSERT_RE.search(body):
                    no_assert += 1
    critical = sorted(f["rel"] for f in src
                      if CRITICAL_RE.search(Path(f["rel"]).stem) and Path(f["rel"]).stem.lower() not in mirrored_src)
    n = len(tests)
    return {
        "method": "heuristic",
        "test_files": n,
        "test_to_source_ratio": (metrics or {}).get("test_to_source_ratio"),
        "assertions": asserts,
        "assertions_per_test_file": _ratio(asserts, n, 1),
        "mock_calls": mocks,
        "mocks_per_test_file": _ratio(mocks, n, 1),
        "mirror_ratio": _ratio(mirrored, n),
        "private_access_in_tests": private,
        "boilerplate_markers": boiler,
        "snapshot_tests": snaps,
        "no_assert_tests": no_assert,
        "critical_untested": critical[:CAP],
    }


def _parse_deps(name, text):
    """-> list of (dep_name, pinned: bool, dev: bool)"""
    deps = []
    low = name.lower()
    if low.startswith("requirements"):
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith(("-", "git+", "http://", "https://")):
                continue
            dep = re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip()
            if dep:
                deps.append((dep.lower(), "==" in line, "dev" in low))
    elif name == "pyproject.toml":
        try:
            import tomllib
            d = tomllib.loads(text)
        except Exception:
            d = {}
        proj = d.get("project") or {}
        for spec in proj.get("dependencies") or []:
            dep = re.split(r"[<>=!~;\[ ]", spec, maxsplit=1)[0].strip()
            deps.append((dep.lower(), "==" in spec, False))
        for group, specs in (proj.get("optional-dependencies") or {}).items():
            for spec in specs:
                dep = re.split(r"[<>=!~;\[ ]", spec, maxsplit=1)[0].strip()
                deps.append((dep.lower(), "==" in spec, True))
        poetry = ((d.get("tool") or {}).get("poetry") or {})
        for group, key in ((False, "dependencies"), (True, "dev-dependencies")):
            for dep, spec in (poetry.get(key) or {}).items():
                if dep.lower() == "python":
                    continue
                ver = spec if isinstance(spec, str) else (spec or {}).get("version", "")
                deps.append((dep.lower(), bool(re.fullmatch(r"=?\d[\w.]*", str(ver))), group))
        for gname, g in ((poetry.get("group") or {})).items():
            for dep, spec in (g.get("dependencies") or {}).items():
                ver = spec if isinstance(spec, str) else (spec or {}).get("version", "")
                deps.append((dep.lower(), bool(re.fullmatch(r"=?\d[\w.]*", str(ver))), True))
    elif name == "package.json":
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            d = {}
        for key, dev in (("dependencies", False), ("devDependencies", True)):
            for dep, ver in (d.get(key) or {}).items():
                deps.append((dep.lower(), bool(re.fullmatch(r"\d[\w.-]*", str(ver))), dev))
    elif name == "go.mod":
        for m in re.finditer(r"^\s*([\w./-]+)\s+v[\w.+-]+(.*)$", text, re.M):
            if "// indirect" in m.group(2):
                continue
            if m.group(1) in ("module", "go", "toolchain", "require"):
                continue
            deps.append((m.group(1).lower(), True, False))
    elif name == "Cargo.toml":
        try:
            import tomllib
            d = tomllib.loads(text)
        except Exception:
            d = {}
        for key, dev in (("dependencies", False), ("dev-dependencies", True), ("build-dependencies", True)):
            for dep, spec in (d.get(key) or {}).items():
                ver = spec if isinstance(spec, str) else (spec or {}).get("version", "")
                deps.append((dep.lower(), str(ver).startswith("="), dev))
    elif name == "pom.xml":
        for m in re.finditer(r"<dependency>(.*?)</dependency>", text, re.S):
            aid = re.search(r"<artifactId>([^<]+)</artifactId>", m.group(1))
            ver = re.search(r"<version>([^<]+)</version>", m.group(1))
            scope = re.search(r"<scope>([^<]+)</scope>", m.group(1))
            deps.append(((aid.group(1) if aid else "?").lower(),
                         bool(ver and "${" not in ver.group(1)),
                         bool(scope and scope.group(1) == "test")))
    elif name.startswith("build.gradle"):
        for m in re.finditer(r"^\s*(implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly)\s*\(?\s*['\"]([^'\"]+)['\"]", text, re.M):
            coord = m.group(2)
            parts = coord.split(":")
            deps.append(((parts[1] if len(parts) > 1 else coord).lower(),
                         len(parts) >= 3 and not parts[2].startswith("$"),
                         m.group(1).startswith("test")))
    elif name == "Package.swift":
        for m in re.finditer(r"\.package\(\s*(?:name:\s*\"[^\"]+\",\s*)?url:\s*\"([^\"]+)\"", text):
            deps.append((m.group(1).rstrip("/").rsplit("/", 1)[-1].lower().removesuffix(".git"), "exact:" in text, False))
    return deps


def dependencies_block(manifests, source_loc, is_service):
    if not manifests:
        return None
    direct, all_deps = {}, []
    for name, text in manifests.items():
        deps = _parse_deps(name, text)
        if deps:
            direct[name] = {"runtime": sum(1 for d in deps if not d[2]), "dev": sum(1 for d in deps if d[2])}
            all_deps += deps
    names = {d[0] for d in all_deps}
    dup = [list(p) for p in DUP_PAIRS if p[0] in names and p[1] in names]
    heavy = sorted(n for n in names if any(n == fw or n.startswith(fw + "-") or n.startswith(fw + "_") for fw in FRAMEWORKS)) if is_service is False else []
    total = len(all_deps)
    return {
        "direct": direct,
        "direct_total": total,
        "per_kloc": _ratio(total, source_loc / 1000, 2) if source_loc else None,
        "duplicate_purpose": dup,
        "heavy_for_purpose": heavy[:CAP],
        "pinned_ratio": _ratio(sum(1 for d in all_deps if d[1]), total),
    }


def documentation_block(files, scope, metrics):
    readme = next((p for p in (scope / "README.md", scope / "README.rst", scope / "README", scope / "readme.md") if p.exists()), None)
    rtext = _read(readme) if readme else ""
    docs = [p for d in (scope, scope / "docs", scope / "doc") if d.is_dir()
            for p in d.rglob("*.md") if re.search(r"adr|architecture|design|decision", p.name, re.I)]
    src = [f for f in files if not f["is_test"]]
    py_defs = py_doc = ts_fns = ts_doc = 0
    comment_lines = code_lines = 0
    for f in src:
        lines = f["text"].splitlines()
        cre = COMMENT_LINE["python"] if f["lang"] == "python" else COMMENT_LINE["default"]
        for l in lines:
            if not l.strip():
                continue
            if cre.match(l):
                comment_lines += 1
            else:
                code_lines += 1
        if f["lang"] == "python":
            for m in PY_DEF_RE.finditer(f["text"]):
                if m.group(2).startswith("_"):
                    continue
                py_defs += 1
                rest = f["text"][m.end():].lstrip()
                if rest.startswith(('"""', "'''")):
                    py_doc += 1
        elif f["lang"] in ("typescript", "javascript"):
            for m in TS_EXPORT_FN_RE.finditer(f["text"]):
                ts_fns += 1
                before = f["text"][:m.start()].rstrip().splitlines()[-2:]
                if any(l.strip().endswith("*/") for l in before):
                    ts_doc += 1
    cov = {}
    if py_defs:
        cov["python"] = _ratio(py_doc, py_defs)
    if ts_fns:
        cov["typescript"] = _ratio(ts_doc, ts_fns)
    root_names = {p.name.lower() for p in scope.iterdir()} if scope.is_dir() else set()
    return {
        "method": "heuristic",
        "readme_lines": len(rtext.splitlines()),
        "readme_sections": len(re.findall(r"^##\s", rtext, re.M)),
        "has_architecture_doc": bool(docs),
        "docstring_coverage": cov or None,
        "comment_density": _ratio(comment_lines, code_lines),
        "todo_count": (metrics or {}).get("todo_fixme_count"),
        "has_contributing": any(n.startswith("contributing") for n in root_names),
        "has_changelog": any(n.startswith(("changelog", "changes", "history")) for n in root_names),
        "has_license": any(n.startswith(("license", "licence", "copying")) for n in root_names),
    }


def _git(repo, *args, timeout=120):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def history_block(repo, source_loc, limit=5000):
    if _git(repo, "rev-parse", "--is-inside-work-tree") is None:
        return None
    # a trailing \x1f closes the multi-line body so --name-only output can follow it
    log = _git(repo, "log", f"-n{limit}", "--format=%x1e%H%x1f%ae%x1f%ct%x1f%s%x1f%B%x1f", "--name-only")
    if not log:
        return None
    commits = []
    for chunk in log.split("\x1e")[1:]:
        parts = chunk.split("\x1f")
        if len(parts) < 6:
            continue
        commits.append({"sha": parts[0], "author": parts[1], "ts": int(parts[2]), "subject": parts[3],
                        "body": parts[4], "files": [l for l in parts[5].splitlines() if l.strip()]})
    if not commits:
        return None
    first = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    first_added = None
    if first:
        stat = _git(repo, "show", "--numstat", "--format=", first.split()[0])
        if stat is not None:
            first_added = sum(int(l.split("\t")[0]) for l in stat.splitlines()
                              if l.split("\t")[0].isdigit())
    files_per = [len(c["files"]) for c in commits]
    msg_len = [len(c["subject"]) for c in commits]
    ts = [c["ts"] for c in commits]
    days = max((max(ts) - min(ts)) / 86400, 0)
    n = len(commits)
    return {
        "commits": n,
        "authors": len({c["author"] for c in commits}),
        "first_commit_loc_ratio": _ratio(first_added, source_loc, 2) if first_added is not None and source_loc else None,
        "median_files_per_commit": statistics.median(files_per) if files_per else None,
        "big_commits_ratio": _ratio(sum(1 for x in files_per if x > 20), n),
        "median_msg_len": statistics.median(msg_len) if msg_len else None,
        "conventional_prefix_ratio": _ratio(sum(1 for c in commits if CONVENTIONAL_RE.match(c["subject"])), n),
        "ai_coauthor_commits": sum(1 for c in commits if AI_COAUTHOR_RE.search(c["body"])),
        "days_active": round(days, 1),
        "commits_per_active_week": round(n / max(days / 7, 1), 2),
    }


def ai_markers_block(files, scope, history):
    present = [n for n in INSTRUCTION_FILES if (scope / n).exists()]
    generated = []
    for f in files:
        if Path(f["rel"]).name in LOCK_OR_MANIFEST:
            continue
        head = "\n".join(f["text"].splitlines()[:5])
        if GENERATED_RE.search(head):
            generated.append(f["rel"])
    return {
        "instruction_files": present,
        "ai_coauthor_commits": (history or {}).get("ai_coauthor_commits"),
        "generated_headers": {"count": len(generated), "top": generated[:CAP]},
    }


def demand_block(files, manifests, scope, findings):
    src = [f for f in files if not f["is_test"]]
    blob = "\n".join(manifests.values()).lower()
    readme = _read(scope / "README.md") if (scope / "README.md").exists() else ""
    deploy = sum(1 for n in DEPLOY_FILES if (scope / n).exists())
    for d in DEPLOY_DIRS:
        p = scope / d
        if p.is_dir():
            deploy += sum(1 for x in p.rglob("*") if x.is_file() and x.suffix in (".yml", ".yaml", ".tf", ".json"))
    api = sum(1 for p in scope.rglob("*") if p.is_file()
              and not any(part in SKIP_DIRS for part in p.relative_to(scope).parts)
              and (p.suffix in (".graphql", ".gql", ".proto")
                   or re.search(r"openapi|swagger", p.name, re.I) and p.suffix in (".yaml", ".yml", ".json")))
    p01 = Counter()
    for f in (findings or {}).get("findings", []):
        if f.get("severity") in ("P0", "P1") and f.get("status") in ("new", "persisting"):
            p01[f.get("dimension", "?")] += 1
    return {
        "method": "heuristic",
        "concurrency": sum(len(CONCURRENCY_RE.findall(f["text"])) for f in src),
        "security_surface": sum(len(SECURITY_RE.findall(f["text"])) for f in src),
        "data_stores": sorted({d for d in DATA_STORES if d in blob}),
        "external_integrations": {
            "http_libs": sorted({h for h in HTTP_LIBS if re.search(r"\b" + re.escape(h) + r"\b", blob)}),
            "calls": sum(len(HTTP_CALL_RE.findall(f["text"])) for f in src)},
        "deployment": deploy,
        "domain_hard_spots": sum(len(HARD_SPOT_RE.findall(f["text"])) for f in src),
        "public_api": api,
        "users_hint": len(USERS_RE.findall(readme)),
        "open_p0_p1": dict(p01),
    }


def passthrough_block(metrics):
    if not metrics:
        return None
    fn = metrics.get("functions") or {}
    cycles = metrics.get("import_cycles") or {}
    return {
        "functions": {"count": fn.get("count"), "p50": fn.get("p50"), "p90": fn.get("p90"),
                      "max": fn.get("max"), "over_80": len(fn.get("over_80") or [])} if fn else None,
        "duplication_percentage": (metrics.get("duplication") or {}).get("percentage"),
        "coverage_overall": (metrics.get("coverage") or {}).get("overall"),
        "hotspots": [h.get("path") for h in (metrics.get("hotspots") or [])[:5]],
        "complexity_source": metrics.get("complexity_source"),
        "import_cycles": {k: len(v) for k, v in cycles.items() if isinstance(v, list)},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("--audit", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    audit = Path(args.audit)
    profile = _load(audit / "repo-profile.json")
    metrics = _load(audit / "metrics.json")
    findings = _load(audit / "findings.json")
    scope = (repo / ((profile or {}).get("scope") or ".")).resolve()

    files = walk(repo, scope)
    manifests = read_manifests(scope)
    size = size_block(profile, metrics, files)
    history = history_block(repo, size["source_loc"])
    signals = {
        "repo": str(repo), "scope": str(scope.relative_to(repo)) if scope != repo else ".",
        "audit_dir": str(audit),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "size": size,
        "indirection": indirection_block(files, manifests, size["source_loc"]),
        "config_surface": config_block(files, scope),
        "error_handling": error_block(files, metrics),
        "testing": testing_block(files, metrics),
        "dependencies": dependencies_block(manifests, size["source_loc"], size["is_service"]),
        "documentation": documentation_block(files, scope, metrics),
        "history": history,
        "ai_assist_markers": ai_markers_block(files, scope, history),
        "demand_drivers": demand_block(files, manifests, scope, findings),
        "passthrough": passthrough_block(metrics),
    }
    out = Path(args.out) if args.out else audit
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration-signals.json").write_text(json.dumps(signals, indent=2) + "\n")
    ind, err, tst = signals["indirection"], signals["error_handling"], signals["testing"]
    print(f"files {size['file_count']} · source LOC {size['source_loc']} · "
          f"interfaces {ind['interfaces']} ({len(ind['single_impl_interfaces'])} with ≤1 impl) · "
          f"layers/kLOC {ind['layers_per_kloc']} · broad catches {err['broad_catches']} · "
          f"error boundary {err['error_boundary']} · test files {tst['test_files']} "
          f"(mirror {tst['mirror_ratio']}) · deps {(signals['dependencies'] or {}).get('direct_total')} · "
          f"commits {(history or {}).get('commits')} (AI co-authored {(history or {}).get('ai_coauthor_commits')})")
    print(f"wrote {out/'calibration-signals.json'}")


if __name__ == "__main__":
    main()
