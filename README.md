# code-audit

A structured, full-repository code audit skill for Claude Code. Audits across 11 dimensions — design, structure, data flow, security, testing, maintainability, readability, correctness, performance, dependencies/licensing, and operability — producing findings, reports, and interactive dashboards.

Supports Python, TypeScript/JavaScript/Node, Swift, Go, C/C++, Java, and Rust, including mixed-language monorepos.

## Usage

```
/code-audit [triage|standard|deep] [--only dim1,dim2] [--path SUBDIR] [--out DIR]
            [--no-install] [--offline] [--file-issues] [--baseline FILE]
/code-audit compare <auditdir1> <auditdir2> [...]
```

## Pipeline

| Phase | Description | Script |
|-------|-------------|--------|
| 0 | Preflight — detect repo languages, frameworks, structure | `scripts/detect_repo.py` |
| 1 | Tooling — check/install available scanners | `scripts/check_tools.py` |
| 2 | Automated scan — run scanners, compute metrics, normalize | `scripts/run_scanners.py`, `scripts/metrics.py`, `scripts/normalize_findings.py` |
| 3 | Manual review — Claude reviews code per rubrics (skip at triage) | `scripts/fingerprint.py` |
| 4 | Baseline diff — classify findings as new/persisting/fixed | `scripts/baseline.py` |
| 5 | Synthesis & report — narrative + rendered report and dashboard | `scripts/render_report.py`, `scripts/render_dashboard.py` |
| 6 | Issue filing — create GitHub/GitLab issues from findings (optional) | `scripts/file_issues.py` |

## Output

All artifacts land in `.audit/` (or `--out DIR`):

```
.audit/
├── repo-profile.json
├── tool-report.json
├── metrics.json
├── raw/                    # untouched scanner output
├── findings.json           # canonical — everything else is a projection
├── narrative.json
├── baseline.json
├── suppressions.json
├── report.md
├── report.html
├── dashboard.html
└── issues-manifest.json
```

## Tiers

- **triage** — automated scan only, brief synthesis
- **standard** — automated scan + targeted manual review (~10% of source)
- **deep** — full architecture review, end-to-end data-flow tracing, correctness reasoning

## Compare mode

Compare audits across repos or track the same repo over time:

```
/code-audit compare .audit-v1 .audit-v2
```

See `references/portfolio.md` for details.
