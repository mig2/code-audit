---
name: code-audit
description: >-
  Perform a structured, full-repository code audit across design, structure, data flow,
  security, testing, maintainability, readability, correctness, performance,
  dependencies/licensing, and (for services) operability. Use this skill whenever the user
  asks to audit a codebase or repo, review code quality, run a security/tech-debt/health
  review, assess a project before adopting or refactoring it, generate an audit report or
  scorecard, compare audits across repos, or turn audit findings into GitHub/GitLab issues.
  Trigger on phrases like "audit", "code review of the whole repo", "health check",
  "tech debt report", "how good is this codebase", or "/code-audit". Works for Python,
  TypeScript/JavaScript/Node, Swift, Go, C, C++, Java, and Rust, including mixed-language
  monorepos.
---

# code-audit

Audit a repository at a chosen depth tier, producing a canonical `findings.json` from
which all assets (markdown report, polished HTML report, interactive dashboard, tracker
issues) are generated. Deterministic work is done by scripts in `scripts/`; your context
budget is reserved for what only you can do: architecture review, data-flow tracing,
correctness reasoning, and synthesis.

**Read before starting:** `references/dimensions.md` (the rubrics) and the
`references/lang/<x>.md` file for each detected language. Read
`references/severity-and-triage.md` before assigning severities. Read other references
when their phase arrives (noted below).

## Invocation

```
/code-audit [triage|standard|deep] [--only dim1,dim2] [--path SUBDIR] [--out DIR]
            [--no-install] [--offline] [--file-issues] [--baseline FILE]
/code-audit compare <auditdir1> <auditdir2> [...]
/code-audit migrate                   # move flat .audit/ to timestamped layout
```

Default tier: `standard`. Default workspace: `.audit/` in the repo root (ensure it is
gitignored; add to `.gitignore` if missing, after asking). Each audit run is stored in a
timestamped subdirectory (`.audit/YYYYMMDDHHMM/`); prior audits are preserved
automatically. `compare` mode: skip to `references/portfolio.md`. `migrate` mode: run
`python3 scripts/audit_history.py migrate .audit` to convert a flat `.audit/` from a
previous audit into the timestamped layout.

## Tiers

| Tier | Automated scan | Your manual review |
|---|---|---|
| `triage` | Full | None. Normalize, dedupe, write a brief synthesis only. |
| `standard` | Full | Targeted: all security-surface files, top-decile complexity×churn hotspots, entry points, ~10% sample of remaining source (cap ~40 files; scale down for huge repos, up for tiny ones). |
| `deep` | Full | Everything in standard, plus full architecture review, end-to-end data-flow tracing of each major flow, correctness reasoning on critical logic, test-quality review, API design review. Chunk across sessions for large repos; persist progress in `.audit/review-progress.json`. |

Every tier reports against every applicable dimension. Where a tier doesn't assess
something, the report says "not assessed at this tier" — never silently omit.

## Pipeline

Run phases in order. All scripts support `--help`. All write into the audit workspace.

### Phase 0 — Preflight

```bash
AUDIT_DIR=$(python3 scripts/audit_history.py init REPO --out .audit)
python3 scripts/detect_repo.py REPO --out AUDIT_DIR
```

`audit_history.py init` creates a timestamped directory (e.g. `.audit/202606181200/`),
registers it in `.audit/audit-history.json`, and auto-links the baseline to the most
recent completed audit. Use the returned path as `AUDIT_DIR` for all subsequent phases.

`detect_repo.py` produces `repo-profile.json`: languages with LOC share, manifests,
frameworks, build systems, VCS host, sub-projects, service-vs-library classification.
Review it. If sub-projects were detected (monorepo), the audit is **per-project**: each
sub-project gets its own `AUDIT_DIR/<project>/` with its own findings, baseline, and
report, plus a repo-level rollup. Run subsequent phases once per project (scripts accept
`--project NAME` to scope), then build the rollup in Phase 5.

Now read `references/lang/<x>.md` for each detected language (C and C++ share
`c-cpp.md`; TS/JS/Node share `typescript.md`).

### Phase 1 — Tooling

```bash
python3 scripts/check_tools.py --profile AUDIT_DIR/repo-profile.json --out AUDIT_DIR
```

Produces `tool-report.json`. Present the matrix to the user: available / missing /
locally installable. Unless `--no-install`, offer to run:

```bash
bash scripts/install_tools.sh --tools ruff,gosec,...   # user-level only, never sudo
```

Missing tools are recorded as coverage gaps — they flow into the report's
audit-completeness table automatically. Never block on a missing tool. If issue filing
is anticipated, also verify `gh auth status` / `glab auth status` now.

### Phase 2 — Automated scan

```bash
python3 scripts/run_scanners.py --profile ... --tools ... --out AUDIT_DIR   # → raw/
python3 scripts/metrics.py REPO --profile ... --out AUDIT_DIR              # → metrics.json
python3 scripts/normalize_findings.py --raw AUDIT_DIR/raw --profile ... --out AUDIT_DIR
```

`normalize_findings.py` produces `findings.json` with tool-sourced entries, fingerprinted
and deduplicated. Skim `metrics.json` — its hotspot list (complexity × churn) drives your
Phase 3 targeting.

**Checkpoint:** summarize the automated picture for the user (finding counts by
dimension/severity, hotspots, coverage gaps) and confirm the manual-review focus before
spending Phase 3 effort.

### Phase 3 — Manual review (skip at `triage`)

Review code per the rubrics in `references/dimensions.md` and the language files'
risk checklists. Targeting comes from the tier table above plus `metrics.json` hotspots
and the repo's security surfaces (entry points, auth, deserialization, SQL, file/network
I/O — the language files enumerate these per ecosystem).

Append your findings to `findings.json` via:

```bash
python3 scripts/fingerprint.py add-finding AUDIT_DIR/findings.json --json '{...}'
```

Your findings use `source: "claude-review"`, a rule of the form `claude.<topic>`, and a
**deterministic key** for fingerprinting: `<primary symbol or path>:<issue-kind>` — write
it the same way a re-run would, so idempotency holds. Be honest with `confidence`; use
`low` freely for suspicions worth a human look. Severity/effort rules:
`references/severity-and-triage.md`.

### Phase 4 — Baseline diff

```bash
python3 scripts/baseline.py AUDIT_DIR/findings.json --out AUDIT_DIR
```

Baseline auto-links to the previous audit's findings via the manifest — no manual
`--baseline` flag needed. Use `--baseline FILE` to override. Classifies findings
`new | persisting | fixed` (and applies `suppressions.json` if present). First run:
offer to write `baseline.json` and recommend committing `suppressions.json` to the repo.

### Phase 5 — Synthesis & report

Read `references/reporting.md` now. Write the narrative blocks (executive summary,
per-dimension assessments with letter grades A–F, top risks, recommended sequencing) into
`AUDIT_DIR/narrative.json` (schema in reporting.md), then:

```bash
python3 scripts/render_report.py AUDIT_DIR      # → report.md, report.html
python3 scripts/render_dashboard.py AUDIT_DIR   # → dashboard.html (auto-populates history from manifest)
python3 scripts/audit_history.py register AUDIT_DIR
```

The dashboard automatically includes trend charts from all prior audits via the manifest.
`audit_history.py register` marks this audit as complete in the manifest.

For monorepos, also render each project then build the rollup:
`python3 scripts/render_report.py AUDIT_DIR --rollup`.

**Checkpoint:** present `report.md` (and the HTML files) to the user. Never proceed to
issues without this review.

### Phase 6 — Issue filing (optional, on request or `--file-issues`)

Read `references/issue-filing.md`, then:

```bash
python3 scripts/file_issues.py AUDIT_DIR --host github|gitlab --repo OWNER/NAME --dry-run
```

Always run `--dry-run` first and show the user the plan (hierarchy, label mapping,
rollup batching) before running without it. The script is idempotent: it consults
`issues-manifest.json` and searches issue bodies for fingerprint markers; persisting
findings get a comment, not a duplicate.

## Hard rules

- Never run scanners or installs outside the target repo and audit workspace.
- Never file issues, create labels, or comment on trackers without explicit user
  confirmation of the dry-run plan in this session.
- Never present a tool-skipped check as assessed. Coverage honesty is a feature.
- Findings you author must cite concrete evidence (file:line, snippet) — no vibes-only
  findings above `confidence: low`.
- Do not "fix" the code during an audit unless asked; the audit's output is findings.
- Respect `--offline`: skip network-dependent scanners and record the gap.

## Workspace layout

```
.audit/                               # audit root; ensure gitignored
├── audit-history.json                # manifest of all audits
├── suppressions.json                 # repo-level suppressions
├── YYYYMMDDHHMM/                     # one per audit run
│   ├── repo-profile.json  tool-report.json  metrics.json
│   ├── raw/<tool>.{json,txt}         # untouched scanner output
│   ├── findings.json                 # canonical — everything else is a projection
│   ├── narrative.json                # your synthesis blocks
│   ├── baseline.json  issues-manifest.json
│   ├── report.md  report.html  dashboard.html
│   └── review-progress.json          # deep-tier chunking state
```

## Reference index

- `references/dimensions.md` — rubrics for all 11 dimensions; per-tier depth expectations
- `references/severity-and-triage.md` — P0–P3/INFO definitions, confidence, effort, batching eligibility
- `references/reporting.md` — report structure, narrative.json schema, grading guidance
- `references/issue-filing.md` — GitHub sub-issues / GitLab strategy, label adaptation, batching
- `references/portfolio.md` — compare mode (cross-repo and same-repo-over-time)
- `references/lang/{python,typescript,swift,go,c-cpp,java,rust}.md` — tool matrices, strictness escalation, risk checklists, idiom rubrics
