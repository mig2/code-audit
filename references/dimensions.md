# Audit dimensions — rubrics

Eleven dimensions: ten core + **operability** (applied only when `repo-profile.json` has
`"is_service": true`). Each rubric: what good looks like → what to examine → common
failure modes → per-tier depth. Deterministic inputs come from Phase 2; everything under
"examine" is your Phase 3 work.

Severity and effort assignment: see `severity-and-triage.md`. Every finding needs
evidence (file:line + snippet) and a recommendation.

---

## 1. Design

**Good looks like:** abstractions that match the domain; dependencies point in one
direction; components replaceable without cascading edits; no speculative generality;
framework used the way it wants to be used.

**Examine:** the dependency graph (Phase 2 emits import cycles and layering hints);
public API surfaces — are they minimal and coherent?; the 3–5 central abstractions — do
they pull their weight?; extension points actually used vs. YAGNI scaffolding; backward
compatibility posture of public APIs (semver discipline, deprecation paths).

**Failure modes:** god objects/modules; circular dependencies; business logic in I/O
layers (handlers, views, controllers); leaky abstractions (callers reaching through
layers); inheritance where composition fits; config/feature-flag sprawl substituting for
design; "util" modules as dumping grounds.

**Tiers:** triage — cycles and layering from tools only. standard — review the central
abstractions and worst graph offenders. deep — full architecture review: draw the
intended architecture from README/docs, compare with the actual graph, document drift.

## 2. Structure

**Good looks like:** a newcomer finds things where they'd look first; directory names
describe domain, not plumbing; file and function sizes have sane distributions; no dead
code rotting in place.

**Examine:** top-level layout vs. the project's own stated organization; outliers in the
size distributions from `metrics.json` (files > ~800 LOC, functions > ~80 LOC are review
candidates, not automatic findings); dead/unreachable code reports; test placement
conventions; generated-code separation.

**Failure modes:** mirror-image trees (`src/x` + `tests/x` drifting apart); circular
package layouts forcing import tricks; one-class-per-microfile noise or
everything-in-one-file sprawl; stale feature directories; build artifacts committed.

**Tiers:** triage — metrics outliers only. standard — walk the tree, sample 2–3 areas a
newcomer would touch first. deep — full tree review plus "where would I add feature X?"
thought experiments for 2–3 plausible features.

## 3. Data flow

**Good looks like:** every external input crosses an explicit validation boundary once,
near entry; trust boundaries are identifiable; state mutation is localized; concurrent
access to shared data is disciplined; serialization formats versioned.

**Examine:** trace each major flow end-to-end (request → handler → logic → store;
file/queue in → transform → out). Where does data enter? Where is it validated, and is
validation *before* first use? Where does it cross process/network/serialization
boundaries? Which data is shared across threads/tasks/goroutines, and under what
discipline? PII: where does personal data enter, persist, log, and leave?

**Failure modes:** validation scattered or duplicated per call-site; trusting internal
callers with external data ("it was validated upstream" — was it?); shared mutable
singletons; reads of partially-written state; logging PII/secrets; deserializing
attacker-controlled formats (pickle, ObjectInputStream, NSCoding without secure coding).

**Tiers:** triage — taint-tool output only (semgrep dataflow where rules ran). standard —
trace the 2–3 highest-value flows. deep — trace every major flow; produce a
trust-boundary inventory in the report.

## 4. Security

**Good looks like:** authn/authz enforced at a chokepoint, not per-endpoint by
convention; injection-prone sinks always parameterized; secrets out of code and logs;
crypto via vetted libraries with sane parameters; dependencies vuln-scanned.

**Examine (beyond tool findings):** the auth model — find the chokepoint or prove it's
per-route and audit route coverage; every SQL/shell/template/path construction near user
input; secrets handling (env? vault? committed? logged?); crypto choices (algorithms,
modes, IV/nonce reuse, key storage, comparisons — timing-safe?); upload/download paths
(traversal, content-type, size limits); SSRF surfaces (user-influenced URLs fetched
server-side); language-specific lists in `lang/*.md`.

**Failure modes:** authz checks missing on "internal" endpoints; string-built SQL "just
this once"; `verify=False`/disabled TLS checks; home-rolled crypto or JWT validation;
secrets in git history (gitleaks covers current + history); error messages leaking
internals; CORS `*` with credentials.

**Tiers:** triage — SAST + dep-vuln + secret-scan output, deduplicated and triaged for
false positives you can rule out from the snippet alone. standard — manual review of all
security-surface files. deep — add a written threat-model sketch (assets, actors, entry
points) and verify the top abuse paths.

## 5. Testing

**Good looks like:** critical paths covered by tests that assert behavior, not
implementation; tests fail when the code is wrong and pass when refactored; fast enough
to run habitually; fixtures comprehensible.

**Examine:** coverage numbers *by area* (a 70% average hiding 0% on payment logic is the
real finding); read a sample of tests for the most critical module — do assertions check
outcomes or mock-call counts?; edge/boundary cases (empty, max, unicode, concurrent);
error-path coverage; flakiness markers (retries, sleeps, time/network dependence); test
runtime and CI wiring.

**Failure modes:** assertion-free "smoke" tests inflating coverage; over-mocking until
the test tests the mocks; golden-file tests nobody re-verifies; shared mutable fixtures;
testing private internals (refactor-hostile); no tests for the bug-shaped code (parsers,
date math, money).

**Tiers:** triage — coverage + counts + runtime only. standard — read tests for 2–3
critical modules. deep — test-quality review across the suite; mutation-testing if
tooling exists for the language and the user approves the runtime cost.

## 6. Maintainability

**Good looks like:** a competent newcomer ships a small change within a day; complexity
concentrated where the domain is genuinely complex; docs answer "why"; build/CI is
one-command reproducible; upgrades aren't terrifying.

**Examine:** hotspots (complexity × churn from `metrics.json`) — these files are where
maintenance dollars go; duplication report (is it incidental or structural?); README/doc
adequacy: setup, architecture, "why" comments at the weird parts; ADRs or their absence;
bus factor (git authorship concentration on critical files); CI health (build time,
flakiness); dependency freshness; TODO/FIXME census age.

**Failure modes:** the One File everyone fears; copy-paste families that must be edited
in sync; setup folklore living in one person's head; commented-out code as version
control; docs describing a previous architecture; pinned-and-forgotten dependencies.

**Subareas to call out explicitly:** documentation quality; CI/build health.

**Tiers:** triage — metrics only. standard — review top-5 hotspots + README/setup-doc
walkthrough. deep — add bus-factor analysis, dependency-upgrade-path assessment, and an
onboarding simulation ("execute the README from scratch" reasoning).

## 7. Readability

**Good looks like:** names say what things are; functions say what they do at one level
of abstraction; control flow followable without a debugger; idiomatic for the language;
comments explain why, not what.

**Examine (sampled — never exhaustive):** the files you already read for other
dimensions, scored against the language's idiom rubric (`lang/*.md`); naming quality at
the API boundary; nesting depth and early-return discipline; comment quality on the
gnarly parts; consistency (one style throughout beats the better style applied 60%).

**Failure modes:** abbreviations only the author decodes; boolean parameters changing a
function's meaning; clever one-liners at load-bearing points; lying names
(`get_user` that creates one); mixed paradigms mid-module; formatter absent or unenforced.

**Tiers:** triage — linter/formatter conformance numbers only. standard — score your
Phase 3 sample. deep — same, larger sample, plus public-API naming review.

## 8. Correctness

**Good looks like:** the type system used honestly (no escape-hatch saturation); errors
handled or deliberately propagated, never swallowed; boundaries (off-by-one, empty,
overflow) respected; resources have owners; concurrency primitives used correctly.

**Examine:** type-checker/compiler output at maximum strictness (the lang files give the
escalation incantations — run against the repo without demanding it adopt them; findings
are advisory); error-handling completeness in the critical paths (what happens on the
failure branch — is there one?); the bug-shaped code: parsers, date/time/timezone math,
money/decimal arithmetic, pagination, retries/idempotency; resource lifecycle (files,
sockets, locks, transactions — every acquire has a guaranteed release?); concurrency:
shared state inventory × synchronization discipline.

**Failure modes:** swallowed exceptions (`except: pass` and cousins); float money;
naive-datetime arithmetic across DST; unchecked integer narrowing; TOCTOU patterns;
retry without idempotency; partial writes without transactions; lock ordering hazards.

**Tiers:** triage — tools only. standard — review error handling + one critical
algorithm end-to-end. deep — correctness reasoning on every critical algorithm,
concurrency review, resource-lifecycle audit.

## 9. Performance

**Good looks like:** algorithmic complexity sane for realistic n on hot paths; I/O
batched where it counts; no synchronous stalls on async paths; caching deliberate, with
an invalidation story; measurement harness exists for anything tuned.

**Examine:** hot paths first — identify them from the architecture (request handlers,
inner loops, large-data transforms), then reason about complexity against realistic
sizes; N+1 patterns (queries-in-loops, RPC-in-loops); allocation/copy behavior where the
language makes it expensive; sync-on-async (blocking calls inside async handlers /
event loops); cache usage and invalidation hazards; presence of
benchmarks/profiles — tuning without measurement is itself a finding.

**Failure modes:** O(n²) "temporary" scans on growing data; per-item DB/API calls;
unbounded in-memory accumulation of streamable data; regex catastrophes on
user input; chatty serialization at internal boundaries; premature micro-optimization
obscuring the actual hotspot.

**Tiers:** triage — anti-pattern rules (semgrep perf packs, clippy perf) only.
standard — reason through the 2–3 hottest paths. deep — all major paths, plus a
"where would this fall over at 10× load/data" assessment.

## 10. Dependencies & licensing

**Good looks like:** every dependency earns its place; lockfiles committed and honored;
licenses inventoried with no copyleft surprises against the project's own license;
critical deps maintained and pinned with an upgrade cadence.

**Examine:** license inventory output — flag GPL/AGPL/SSPL-family in
permissive/proprietary projects, and unknown-license deps; freshness/abandonment (last
release, archived repos, single-maintainer criticals); transitive weight (does a CLI
really need 600 packages?); lockfile hygiene (present, committed, in sync with
manifest); vendored code provenance; "could this dep be 30 lines?" for trivial ones;
vuln-scan results (shared with Security — file under Security, cross-reference here).

**Failure modes:** no lockfile; lockfile drift; abandoned criticals; license-unknown
deps shipped commercially; duplicate deps doing the same job; typosquat-shaped names;
git-URL dependencies pinned to branches.

**Tiers:** triage — full (this dimension is mostly deterministic). standard — add
judgment review of the top-10 criticals. deep — add upgrade-path assessment and
supply-chain posture (publish provenance, CI pinning).

## 11. Operability (services only)

**Good looks like:** a 3am incident is debuggable from logs/metrics alone; config comes
from the environment with documented keys and sane defaults; secrets never in config
files; the service starts, stops, and degrades gracefully.

**Examine:** log quality at failure points — pick three plausible failures, find the log
lines they'd produce, judge whether they'd suffice; structured vs. printf logging;
metrics/tracing on the critical path; health/readiness endpoints; config-source
inventory (env/file/flags, precedence, secret separation); shutdown handling (drains
in-flight work? releases locks?); startup ordering and dependency checks; deploy
artifacts (Dockerfile hygiene, resource limits).

**Failure modes:** error logs without identifiers/context; secrets in env dumps or
startup logs; no readiness distinct from liveness; SIGTERM = data loss; config defaults
that only work on the author's machine; log level frozen at DEBUG (or ERROR) in prod.

**Tiers:** triage — censuses only (logging calls, config sources, health endpoints).
standard — the three-failures log walkthrough + config review. deep — full incident
simulation reasoning + deploy-artifact review.

---

## Cross-cutting instructions

- **One finding, one dimension.** Pick the dimension of the *fix*, cross-reference in
  the description if it touches others (vuln scans → security; license issues →
  dependencies).
- **False-positive hygiene:** when you can rule out a tool finding from the snippet and
  surrounding code, set `status: "suppressed"` with a reason rather than deleting it.
  When you can't rule it out, keep it and adjust `confidence`.
- **Positive findings are allowed and valuable:** the report narrative should name what
  the codebase does *well* per dimension; this calibrates trust in the criticisms. These
  go in `narrative.json`, not `findings.json`.
- **Don't double-count:** a single root cause (e.g., "no input validation layer")
  spawning 15 tool findings should become one P1 design/data-flow finding referencing
  the 15, with the 15 kept at INFO linked by `relatedFingerprints`.
