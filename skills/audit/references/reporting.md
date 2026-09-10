# Reporting — structure, narrative schema, grading

Both renderings (`report.md`, `report.html`) are projections of `findings.json` +
`metrics.json` + `narrative.json`. The scripts assemble all tables; you write only the
narrative blocks. Do not hand-build tables the renderer already builds.

## narrative.json schema

```jsonc
{
  "title": "Audit of <repo> — 2026-06",
  "tier": "standard",
  "executive_summary": "3–6 paragraphs, markdown. Lead with the overall verdict...",
  "scorecard": [
    { "dimension": "security", "grade": "C+",
      "summary": "One-or-two-sentence justification.",
      "assessed": true },          // false → renderer prints 'not assessed at this tier'
    ...                            // one entry per applicable dimension
  ],
  "top_risks": [                   // ≤10, ordered
    { "title": "...", "fingerprints": ["sha256:..."], "why": "1–3 sentences" }
  ],
  "strengths": [ "markdown bullets — what the codebase does well" ],
  "sequencing": "markdown — the recommended order of work, per severity-and-triage.md",
  "dimension_notes": { "security": "markdown narrative for the dimension section", ... },
  "coverage_notes": "markdown — anything beyond the auto-generated completeness table"
}
```

## Grading (A–F per dimension)

Grade the dimension's *state*, not the finding count (a well-tested repo with one P0
test gap can still be a B). Anchors:

- **A** — exemplary; you'd show it as a reference. Findings, if any, are P3 polish.
- **B** — solid; gaps are bounded and known. No P0/P1 in this dimension.
- **C** — adequate with real weaknesses; P1s exist or P2s are systemic.
- **D** — dimension is a liability; multiple P1s or a structural P1 root cause.
- **F** — dimension effectively absent or actively dangerous (any unmitigated P0 here).

Use +/− freely. Grade only what the tier assessed; otherwise `"assessed": false`.

## Report structure (renderer-fixed; for your awareness)

1. Header: repo, date, tier, commit hash, auditor line.
2. Executive summary (yours).
3. Scorecard table (grades + one-liners, yours; counts auto-appended).
4. Top risks (yours, hyperlinked to findings).
5. Strengths (yours).
6. Findings by dimension: auto tables sorted P0→P3, status-tagged (new/persisting),
   confidence-separated; your `dimension_notes` lead each section.
7. Recommended sequencing (yours).
8. Metrics appendix (auto).
9. Audit completeness (auto from tool-report + skips; plus your `coverage_notes`).
10. Suppressed findings appendix (auto, collapsed).

## Writing guidance

- Executive summary opens with the verdict a CTO needs: ship-shape / needs scheduled
  work / stop-and-fix. Then the three things that most determine that verdict.
- Every criticism in narrative text must trace to a finding (cite fingerprints); every
  P0/P1 finding must surface in either top-risks or its dimension note.
- Prose, not bullet spam, in the narrative blocks; the renderer provides all the tables
  the reader needs.
- Monorepo rollup (`render_report.py --rollup`): you additionally write a short
  `rollup-narrative.json` ({"executive_summary", "comparison_notes"}) — the per-project
  scorecards are aggregated automatically.

## Dashboard

`render_dashboard.py` needs no input from you. It embeds findings + metrics into a
single-file HTML app: filters (dimension/severity/status/confidence/language/project),
severity-over-time chart when ≥2 audits' findings files are passed via `--history`,
hotspot treemap from metrics. Mention to the user that it's self-contained and safe to
share internally.
