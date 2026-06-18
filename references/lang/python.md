# Python

## 1. Detection signals
`pyproject.toml`, `setup.py|cfg`, `requirements*.txt`, `Pipfile`, `poetry.lock`,
`uv.lock`, `*.py`. Frameworks: django (`manage.py`, `settings.py`), flask/fastapi
(imports), celery, airflow (dags/). Service signal: ASGI/WSGI entry points, Dockerfile
running gunicorn/uvicorn.

## 2. Tool matrix (invocations as run_scanners.py issues them)

| Purpose | Tool | Invocation | Output |
|---|---|---|---|
| Lint | ruff | `ruff check --output-format json .` | JSON |
| Format conformance | ruff | `ruff format --check .` | text (count) |
| Types | mypy | `mypy --output json .` (fallback: text) | JSON lines |
| SAST | bandit | `bandit -r SRC -f json` | JSON |
| SAST (rules) | semgrep | `semgrep scan --config p/python --config p/security-audit --json` | JSON |
| Dep vulns | pip-audit | `pip-audit -f json` (needs resolvable env; else `-r requirements.txt`) | JSON |
| Dep vulns (alt) | osv-scanner | `osv-scanner scan --format json -r .` | JSON |
| Licenses | pip-licenses | `pip-licenses --format=json --with-urls` (env-dependent) | JSON |
| Complexity | radon | `radon cc -j SRC` / `radon mi -j SRC` | JSON |
| Coverage | coverage/pytest-cov | `pytest --cov --cov-report=json` **only with user approval to run tests** | JSON |
| Secrets | gitleaks | `gitleaks detect --report-format json` | JSON |
| Dead code | vulture | `vulture SRC --min-confidence 80` | text |

Local install: `pipx install X` or `pip install --user X` or `uv tool install X`.

## 3. Strictness escalation (advisory run, not a demand on the repo)
- `mypy --strict --warn-unreachable --warn-redundant-casts` — report delta vs. repo's own config as "type-honesty gap".
- `ruff check --select ALL --statistics` — census of what the repo's config silences; flag only meaningful families (B, S, ASYNC, DTZ, PT).
- Count `# type: ignore`, `# noqa`, `Any` annotations, `cast(` — escape-hatch density per kLOC.

## 4. Risk checklist (manual review)
**Security/data flow:** `eval`/`exec`/`compile` on non-literals; `pickle`/`shelve`/`dill`
loads of external data; `yaml.load` without `SafeLoader`; `subprocess` with `shell=True`
or list-built-from-input; SQL via f-string/`%`/`.format` (vs. params); `requests(...,
verify=False)`; tarfile/zipfile extraction without member sanitization (path traversal);
Jinja2 `autoescape=False`; Django: raw SQL, `mark_safe`, `ALLOWED_HOSTS=['*']`,
DEBUG-in-prod signals; secrets in `settings.py`.

**Correctness:** mutable default arguments; `except:`/`except Exception: pass`;
naive-vs-aware datetime mixing, `datetime.utcnow()` (deprecated, tz-naive); float
arithmetic on money (want `decimal`); `is` for value comparison; late-binding closures in
loops; `dict` mutation during iteration; `asyncio`: blocking calls in coroutines
(`time.sleep`, sync `requests`, file I/O), fire-and-forget tasks without exception
handling, missing `await` (ruff ASYNC/B rules catch some — verify the rest).

**Performance:** N+1 ORM queries (Django: missing `select_related`/`prefetch_related`;
SQLAlchemy: lazy loads in loops); string concat in loops; `pandas` row-wise `apply` on
hot paths; loading whole files where streaming fits.

**Packaging/deps:** `requirements.txt` without pins or lockfile; `setup.py` arbitrary
code; multiple competing dependency declarations drifting.

## 5. Idiom rubric
Comprehensions over map/filter chains where readable; context managers for every
resource; dataclasses/pydantic over dict-blobs for structured data; pathlib over
os.path; f-strings; explicit `__all__`/underscore privacy on modules with public APIs;
type hints on public functions; EAFP where natural but never as exception-swallowing;
docstrings on public API (one-liners fine). Anti-idioms: getattr/setattr gymnastics
without need, `**kwargs` pass-through stacks, isinstance ladders where dispatch fits.
