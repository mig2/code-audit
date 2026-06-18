# Portfolio mode — comparing audits

`/code-audit compare <dir1> <dir2> [...]` operates on **completed audit workspaces**
(each containing `findings.json`, `metrics.json`, `narrative.json`, `repo-profile.json`).
No re-scanning.

```bash
python3 scripts/compare_audits.py DIR1 DIR2 [...] --out OUTDIR
```

Produces `comparison.md` + `comparison.html` with auto-built tables; you write a short
`comparison-narrative.json` ({"summary", "caveats", "recommendations"}).

## What the script computes

- **Scorecard matrix**: dimension grades side-by-side (from each narrative.json).
- **Normalized density**: findings per 1k LOC, by severity and by dimension — the
  normalization that makes a 5k-line repo comparable to a 500k-line one. Confidence-low
  findings excluded from headline densities (shown separately).
- **Common-weakness table**: rules / claude-topics appearing in ≥half the repos, with
  per-repo counts. This is the org-level signal: shared lint configs, conventions, or
  training fix these cheaper than N individual issues.
- **Outliers**: best/worst repo per dimension by grade then density.
- **Same-repo trend detection**: when ≥2 dirs share a repo identity (remote URL in
  repo-profile), the script switches those into trend mode — new/fixed/persisting flows
  between audits, severity counts over time. This also feeds the dashboard `--history`.

## Same-language cohorts

When all compared repos share a primary language, the script adds language-specific
metric comparisons that don't normalize across languages (e.g., Swift force-unwrap
density, Go `interface{}`/`any` density, Rust `unsafe` block counts, TS `any` density —
emitted by metrics.py per language). Mention in your narrative when a cohort mixes
languages and these sections are therefore absent.

## Your narrative duties

- **Caveats first-class**: comparability limits — different domains, ages, team sizes,
  criticality. A worse-scoring repo may be the harder problem. Never rank without this
  paragraph.
- **Recommendations at the org level**: prefer "adopt X convention/config everywhere"
  over per-repo repetition when the common-weakness table supports it.
- Keep it short: the matrix does the talking; one page of prose.
