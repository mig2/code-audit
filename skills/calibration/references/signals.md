# Proportionality signals — per area

For each area: what *fitted* looks like, the over-built and under-built tells, which
`calibration-signals.json` block feeds it, and what to read by hand. The verdict is
always relative to the repo's **purpose and stakes** (Phase 1) — the same structure can be
over-built for a weekend tool and under-built for a payments service.

Evidence rule: every verdict cites at least two concrete locations (`path:line — what`).
Signals get you to the right files; the verdict comes from reading them.

---

## 1. Abstraction (`indirection`)

**Fitted:** the number of layers matches the number of things that actually vary. Every
interface has ≥2 real implementations or a documented external reason (test double for an
external system counts; "future flexibility" does not). Names describe the domain
(`Invoice`, `RateLimiter`), not the pattern (`InvoiceManagerFactory`).

**Over-built:** `single_impl_interfaces` non-empty in a repo under ~20 kLOC; `di_frameworks`
present in a CLI or script; `pattern_named_files` high (Manager/Provider/Handler/Impl);
`layers_per_kloc` > ~3; generic parameters on types instantiated once; a plugin or
strategy system with one plugin; base classes with one subclass; deep `max_dir_depth` for
the file count. Read: the three most central classes and count how many files you open to
follow one request.

**Under-built:** everything in one or two files with no seams; business rules inline in
handlers/views; the same 30-line block in several places (`passthrough.duplication_percentage`);
no data types at all (dicts/maps everywhere, stringly-typed); `hotspots` concentrated in
one file that also has the highest churn. Read: the biggest source file top to bottom.

## 2. Configurability (`config_surface`)

**Fitted:** the things that differ between environments (URLs, secrets, sizes) come from
the environment or one config file with documented keys and defaults; the things that
never change are constants in code.

**Over-built:** config keys that have a single value across all environments; feature
flags (`feature_flags`) that are never false — or never true; a config system with
layering/precedence for a single-deployment app; CLI with dozens of flags nobody passes;
YAML that configures the *structure* of the program. Read: grep each config key's uses.

**Under-built:** hard-coded URLs, paths, credentials (`env_reads` = 0 in a service; check
findings.json for secret-scan hits); "change this line before deploying" comments;
different behavior obtained by editing code; no defaults so the app fails without a
complete config. Read: the startup/entry file.

## 3. Error handling (`error_handling`)

**Fitted:** errors are handled where something can be done about them and propagated
otherwise; there is one boundary (`error_boundary`) that turns unexpected failures into a
logged, identifiable event; expected failures have specific types or codes.

**Over-built:** a custom exception hierarchy (`custom_exception_types` ≫ distinct handling
sites) where callers catch the base anyway; retries, circuit breakers, and fallbacks for
calls that are local and cannot fail; Result/Either wrappers around code that never
errs; error codes catalogued but never mapped to behavior. Read: pick three custom
exceptions and find where each is caught.

**Under-built:** `broad_catches` and `empty_catches` on the paths that matter; `print_debugging`
in place of logging; `unwraps`/`panics`/`err_discards` on I/O; no `error_boundary` in a
service; failures that leave partial writes; "An error occurred" messages with no
identifier. Read: the failure branch of the most important write path.

## 4. Testing (`testing`, `passthrough.coverage_overall`)

**Fitted:** the bug-shaped code (money, dates, parsers, auth, concurrency) is tested at
its boundaries; tests assert outcomes; the suite runs in under a few minutes; mocks stand
in for external systems only.

**Over-built:** `mocks_per_test_file` high and assertions mostly on mock calls; `mirror_ratio`
≈ 1.0 with `private_access_in_tests` (tests coupled to internals, refactor-hostile);
`boilerplate_markers` on trivial tests; `snapshot_tests` nobody re-verifies; 95% coverage
of getters while `critical_untested` is non-empty; test infrastructure (builders,
factories, fixture DSLs) larger than the code under test. Read: the test file for the most
critical module — does any assertion check a business outcome?

**Under-built:** `test_to_source_ratio` near 0; `no_assert_tests`; tests that only prove
the code runs; `critical_untested` non-empty; no tests for error paths; tests skipped or
commented out; coverage file present but stale. Read: `critical_untested` files' entry points.

**L0 tell in this area:** tests that reproduce the implementation's steps and assert the
same intermediate values the code computes — they pass because they are the code.

## 5. Tooling and CI (`demand_drivers.deployment`, `history`, `documentation`)

**Fitted:** one command builds, one runs tests, one deploys; CI runs what a developer
would run; formatter and linter enforced, not aspirational.

**Over-built:** a multi-stage pipeline with matrix builds for a single-platform tool;
release automation for software with one deployer; monorepo tooling for one package;
pre-commit hooks that take longer than the change. Read: the CI config and count jobs
against the number of contributors (`history.authors`).

**Under-built:** no CI; no lockfile; setup steps that live in someone's head
(`readme_sections` low, no `has_contributing`); formatter absent so diffs are noise;
`big_commits_ratio` high (changes land as bulk dumps). Read: the README's setup section
and try to follow it in your head.

## 6. Dependencies (`dependencies`)

**Fitted:** each dependency does a job the standard library or ten lines could not;
pinned via a lockfile; no two dependencies for the same job.

**Over-built:** `duplicate_purpose` pairs; `heavy_for_purpose` (a web framework in a
library, an ORM for one table); `per_kloc` high for the purpose; utility libraries used
for one function; abstraction libraries over one backend. Read: the manifest with the
README beside it, and ask of each dependency "what would break without it".

**Under-built:** hand-rolled HTTP clients, date parsing, CSV, argument parsing, retry
loops where a standard library exists; vendored copies of packages; `pinned_ratio` = 0 in
an application (libraries may legitimately float). Read: the largest "utils" module.

## 7. Documentation (`documentation`)

**Fitted:** README answers what/why/how-to-run in under two screens; the weird parts have
a "why" comment; architecture written down once where it is non-obvious; docstrings on the
public API.

**Over-built:** `comment_density` high with comments that restate the code
(`# increment counter`); docstrings on every private one-liner; generated API docs for an
internal tool; multiple overlapping docs that drift apart; templates left in
(Contributing/Code of Conduct/Security policy for a solo private repo).

**Under-built:** README missing or a template with placeholders; no architecture note for
a multi-component system; the tricky algorithm has no comment; `docstring_coverage` ≈ 0 on
a published library; setup folklore. Read: the README against the actual entry points.

**L0 tell in this area:** README register mismatch — polished marketing or tutorial prose
next to code in a different voice; or an exhaustive README that documents features the
code does not have.

## 8. Operability (services only; `demand_drivers`, audit findings)

Apply when `size.is_service` is true. Use the audit's operability findings; here the
question is proportionality: **over-built** — tracing, metrics, dashboards and alerting for
a single-user internal tool; **under-built** — a customer-facing service with no health
endpoint, no structured logs, no shutdown handling. Read: what happens on SIGTERM, and what
the logs say when the database is down.

---

## Weighting

The areas are not equal. For the required-vs-evident gap, **testing, error handling and
abstraction** carry most of the weight; documentation and tooling are cheaper to fix and
matter less to safety. An over-built verdict in two areas plus under-built in testing is a
classic L2-pattern-following profile: the layers went in, the discipline did not.

Do not compute a score. Write the per-area verdicts, then reason to the levels.
