---
name: calibration
description: >-
  Assess whether a codebase is built proportionately to its purpose — over-engineered,
  under-engineered, or fitted, area by area — and calibrate ownership: what level of
  engineer the codebase requires to be changed safely, what level evidently built it
  (on a ladder that starts at "AI-assisted, not a software engineer"), and the gap
  between them with a concrete plan. Use this skill whenever the user asks whether a
  codebase is over- or under-designed, "did I build this right", "is this too complex
  for what it does", "what kind of engineer should own this", "how skilled was whoever
  built this", "can I maintain this myself", to assess a codebase they inherited or
  bought, to judge an AI-generated codebase, or "/code:calibration". Complements
  /code:audit (which finds defects); this judges proportionality and ownership.
---

# code:calibration

Answer two questions the audit does not: **is the amount of engineering proportionate to
the problem**, and **who should be holding this codebase versus who evidently built it**.
The output is `calibration.json` (your judgment) rendered to `calibration.md` and
`calibration.html`, stored alongside an audit run in `.audit/<run>/`.

All `scripts/` and `references/` paths here are relative to this skill's directory
(`skills/calibration/` inside the `code` plugin). The audit skill lives beside it at
`../audit/`.

**Read before starting:** `references/ladder.md` (the five levels, crosswalks,
signatures, guardrails) and `references/signals.md` (per-area proportionality rubrics).
Read `references/report.md` when you reach Phase 4.

## Invocation

```
/code:calibration [--audit AUDIT_DIR] [--path SUBDIR] [--out DIR]
```

Default: use the most recent complete run in `.audit/audit-history.json`. If there is
none, tell the user a `triage` audit is needed first (it takes a few minutes and produces
the metrics this skill reads) and offer to run `/code:audit triage` — do not re-implement
scanning here.

## Pipeline

### Phase 0 — Inputs

```bash
python3 scripts/calibration_signals.py REPO --audit AUDIT_DIR      # → calibration-signals.json
```

Also read `AUDIT_DIR/repo-profile.json`, `metrics.json` and skim `findings.json`
(open P0/P1 by dimension). Skim the signals file; note which blocks are null (no git,
no coverage, no manifests) — those become caveats.

### Phase 1 — Purpose (checkpoint)

Read the README, manifests and entry points. Write one paragraph: what the software is
for, who uses it, and what is at stake — data, money, users, uptime, regulation. State
your understanding to the user and **confirm it before continuing**; the required owner
level depends on it more than on anything in the code. Ask directly if the README does
not say who the users are or whether it is deployed.

### Phase 2 — Read

Sample deliberately, using `signals.md` as the guide — roughly 10–15 files:

- the three most central abstractions (`indirection.single_impl_interfaces`,
  `pattern_named_files`, `passthrough.hotspots`)
- the largest source file and the startup/entry file
- the failure branch of the most important write path
- **five test files**, including the ones for `testing.critical_untested`'s neighbours and
  the module with the highest `mocks_per_test_file`
- the manifest beside the README
- `git log --oneline | head -40` and two or three full commit diffs from different eras
  if `history.authors` > 1 or `history.first_commit_loc_ratio` is high

Keep a running list of evidence as `path:line — what it shows`. You will need at least
two per area verdict.

### Phase 3 — Judge

1. Per area, choose *over-built / fitted / under-built* with confidence, relative to the
   Phase 1 purpose. Weighting and tells: `signals.md`.
2. Required owner level from stakes and `demand_drivers` — `ladder.md` "Required owner
   level" table. Name the two or three drivers.
3. Evident author level from the signatures you actually saw — `ladder.md` "Evident author
   level" table and the mapping reminders. Give a range when the evidence spans rungs.
   Apply the guardrails: AI markers alone never yield L0; consistency is the tell; tests
   are the highest-signal area.
4. The gap: direction, what it means in practice, the top risks, and a plan ordered by
   risk reduction per effort (three to six steps; never a hygiene checklist).
5. The rung above: three to six concrete differences between this code and what the next
   level would have done here, and the single cheapest step toward it — `ladder.md`
   "Reading the rung above". Write it even when required and evident match.

### Phase 4 — Write and render

Read `references/report.md`. Write `AUDIT_DIR/calibration.json`, then:

```bash
python3 scripts/render_calibration.py AUDIT_DIR      # → calibration.md, calibration.html
```

**Checkpoint:** present `calibration.md`. Offer the HTML for sharing. If the user
disputes the purpose or a verdict, revise the JSON and re-render — do not argue from the
signals; argue from the evidence lines.

## Hard rules

- Describe the code, never the person. The evident level is a property of the artifact.
- L0 is a legitimate rung. Working software built by a non-engineer is an achievement
  with a support gap; write it that way.
- Every verdict cites at least two `path:line` evidence items. No evidence, no verdict —
  put the hunch in `caveats` as a question.
- Do not derive levels from counts. Signals choose what to read; reading decides.
- Do not fix code, file issues, or run scanners here. Point to `/code:audit` for defects
  and issue filing.
- Confidence is capped at medium for single-author, short-history, or generated-heavy
  repos, and for any area where you read fewer than three files.

## Workspace

```
.audit/<run>/
├── calibration-signals.json     # deterministic inputs (script)
├── calibration.json             # your judgment
└── calibration.md  calibration.html
```

## Reference index

- `references/ladder.md` — L0–L4 with Dreyfus / SFIA / industry crosswalk; required-level drivers; evident-level signatures; guardrails
- `references/signals.md` — per-area fitted / over-built / under-built tells, which signal block feeds each, what to read by hand
- `references/report.md` — calibration.json schema, rendered structure, tone rules
