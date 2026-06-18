# Issue filing — hierarchy, labels, batching, idempotency

`file_issues.py` does the mechanics; this file explains the policy so you can present
the dry-run plan intelligently and adapt when the script reports degraded capabilities.

## Preconditions

- `gh` (GitHub) or `glab` (GitLab) installed and authenticated (`gh auth status`).
- User has confirmed the report (Phase 5 checkpoint) and the dry-run plan.
- `--repo OWNER/NAME` matches the audited repo's remote (script verifies; override with
  `--force-repo` only on explicit user instruction).

## Hierarchy

**GitHub** — native sub-issues:

```
[Audit] <repo> — 2026-06 (standard)          root: scorecard + links
├── [Audit/Security] (N findings)            category parent, sub-issue of root
│   ├── [P0] SQL injection in api/users.py   one issue per finding
│   ├── [P1] ...
│   └── [Audit/Security] rollup: 5 small fixes   (batching, below)
└── [Audit/Correctness] ...
```

Sub-issue linking uses `gh api` GraphQL (`addSubIssue`). If the API rejects (older GHES),
the script falls back automatically to: root issue body gets a task-list of category
links; category bodies get task-lists of finding links. Same visual hierarchy, no native
nesting.

**GitLab** — capability ladder, auto-detected: epics (Premium+: root = epic, categories =
child epics or issues, findings = issues) → else issue links of type "relates to" with
task-list checklists mirroring the GitHub fallback.

Monorepo: project name is namespaced into titles — `[Audit/api-server/Security] ...` —
and a per-project category layer is added only when >1 project has findings.

## Per-issue body (script-generated)

Title: `[P1] <finding title>`. Body: dimension, severity, confidence, effort,
location(s) with permalink to the audited commit, description, recommendation, audit
date/tier, and the idempotency marker:

```html
<!-- ca-fp:sha256:ab3f... -->
```

Never strip that comment when editing issue templates.

## Batching

Per `severity-and-triage.md`: P2/P3 × XS/S findings, ≥4 in a dimension → one rollup
issue for that dimension with a checklist line per finding (location — one-liner —
`ca-fp` marker per line, so later runs can match individual items). P0/P1 never batch.
INFO never files. Threshold configurable: `--rollup-threshold N`, `--no-rollup`.

## Labels — adaptive mapping

1. Script fetches existing labels and proposes a mapping: our taxonomy → existing labels
   by exact/synonym match (`security`→`security`, P1→existing `priority: high`-style
   schemes, `correctness`→`bug` is offered but **not** auto-applied — confirm with user).
2. Gaps are created namespaced: `audit`, `audit:design` ... `audit:operability`; severity
   labels `P0`–`P3` only if no existing priority scheme matched.
3. Every filed issue gets: `audit` + dimension label + severity label. Rollups get
   `audit:rollup` too.
4. The dry-run output includes the full mapping table — show it to the user verbatim and
   get approval before live run.

## Idempotency & sync

Before any creation, the script:
1. Reads `issues-manifest.json` (prior filings).
2. Searches the tracker for `ca-fp:` markers (handles manifest loss / other machines).

Then, per finding status: `new` → create; `persisting` with existing issue → add comment
"still present in <date> audit (tier)"; `fixed` with existing open issue → comment
"not detected in <date> audit" and, with `--close-fixed`, close it. Manifest is updated
with every URL; commit it with the baseline if the user wants cross-machine idempotency.

## Failure handling

Rate limits: script backs off and resumes from the manifest — safe to rerun. Partial
runs are safe for the same reason. If label creation is forbidden (no permission), it
files without labels and reports which were skipped — relay that to the user rather than
retrying.
