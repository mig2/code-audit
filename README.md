# code — codebase assessment plugin for Claude Code

Two skills under one namespace:

- **`/code:audit`** — a structured, full-repository audit across 11 dimensions (design, structure, data flow, security, testing, maintainability, readability, correctness, performance, dependencies/licensing, operability), producing findings, reports, an interactive dashboard, and optional tracker issues.
- **`/code:calibration`** — a proportionality and ownership assessment: is the codebase over- or under-engineered for its problem, what level of engineer should own it, what level of engineer evidently built it, and where the gaps are.

Supports Python, TypeScript/JavaScript/Node, Swift, Go, C/C++, Java, and Rust, including mixed-language monorepos.

## Install

```
git clone https://github.com/mig2/code-audit ~/Code/code-audit
~/Code/code-audit/install.sh        # symlinks ~/.claude/skills/code -> the clone
```

Claude Code loads any plugin directory under `~/.claude/skills/` automatically. Because the install is a symlink, `git pull` is the update. The script also removes the pre-plugin copy at `~/.claude/skills/code-audit/` if present.

## Layout

```
.claude-plugin/plugin.json      # plugin manifest (name: code)
skills/audit/                   # /code:audit — SKILL.md, scripts/, references/, assets/
skills/calibration/             # /code:calibration
tests/                          # pytest suite for the audit scripts (pip install -r requirements-dev.txt)
```

# /code:audit

## Usage

```
/code:audit [triage|standard|deep] [--only dim1,dim2] [--path SUBDIR] [--out DIR]
            [--no-install] [--offline] [--file-issues] [--baseline FILE]
/code:audit compare <auditdir1> <auditdir2> [...]
/code:audit migrate                   # move a flat .audit/ to the timestamped layout
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

All artifacts land in `.audit/` (or `--out DIR`). Each run gets its own timestamped
directory; prior audits are kept and the next run's baseline links to the previous one
automatically.

```
.audit/
├── audit-history.json          # manifest of all audits
├── suppressions.json           # repo-level suppressions
└── YYYYMMDDHHMM/               # one per audit run
    ├── repo-profile.json  tool-report.json  metrics.json
    ├── raw/                    # untouched scanner output
    ├── findings.json           # canonical — everything else is a projection
    ├── narrative.json  baseline.json  issues-manifest.json
    ├── report.md  report.html  dashboard.html
    └── review-progress.json    # deep-tier chunking state
```

## Tiers

- **triage** — automated scan only, brief synthesis
- **standard** — automated scan + targeted manual review (~10% of source)
- **deep** — full architecture review, end-to-end data-flow tracing, correctness reasoning

## Compare mode

Compare audits across repos or track the same repo over time:

```
/code:audit compare .audit-v1 .audit-v2
```

See `skills/audit/references/portfolio.md` for details.
