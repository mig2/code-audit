# Severity, confidence, effort — assignment rules

## Severity

| Level | Definition | Test | Examples |
|---|---|---|---|
| **P0** | Exploitable or actively-losing-data now; or correctness failure on a critical path with realistic trigger | "Would you page someone?" yes | SQLi on a live endpoint; committed live credential; data race corrupting writes; money math in floats on billing path |
| **P1** | Serious risk or defect; not yet known-exploited/triggered but plausible; or structural issue blocking safe change | "Must fix this quarter" | Auth check missing on one internal route; vulnerable dependency with a network-reachable path; swallowed exceptions in payment retry; no tests on the core algorithm |
| **P2** | Real but bounded; degrades quality, velocity, or defense-in-depth | "Should fix, schedule it" | Hotspot file at 2k LOC; coverage gap on secondary path; N+1 on an admin page; abandoned non-critical dep |
| **P3** | Polish; worth doing when nearby | "Fix when touching the file" | Naming inconsistencies; missing docstrings on public API; lint-style findings tools didn't auto-fix |
| **INFO** | Observation, no action demanded | — | Census data; positive notes captured for context; child findings rolled under a root-cause finding |

Severity is about *impact × likelihood in this repo*, not the rule's generic rating.
Downgrade tool defaults when the snippet's context bounds the risk (test-only code,
unreachable path) — and say why in the description. Upgrade when context amplifies it
(the "low" finding sits in the auth middleware).

**Vulnerability scans:** map CVSS ≥9 or known-exploited → P0 *if reachable*, else P1;
CVSS 7–9 → P1 reachable / P2 not; below → P2/P3. Reachability = the vulnerable code path
is plausibly invoked by this repo's usage; if you can't determine it, say so and keep the
higher severity.

## Confidence

- **high** — evidence is conclusive from code alone; a reviewer would not need to run anything.
- **medium** — strong signal, but depends on runtime context or unverified assumptions (named in the description).
- **low** — suspicion worth human eyes; pattern-matched smell; do not let these dominate a report's headline counts (report tables separate them).

Tool findings inherit `high` unless you've examined the snippet and doubt it. Your own
deep-reasoning findings about concurrency or distributed behavior are usually `medium` —
be honest.

## Effort (fix estimate)

| | Meaning |
|---|---|
| XS | < 30 min, mechanical |
| S | < half day, localized |
| M | 1–3 days, one component |
| L | ~1–2 weeks, cross-component |
| XL | Project-sized, needs design |

Effort estimates the *fix*, not the investigation. When a fix has a cheap mitigation and
an expensive proper fix, use the proper fix's effort and name the mitigation in the
recommendation.

## Batching eligibility (consumed by file_issues.py)

A finding is rollup-eligible iff `severity ∈ {P2, P3}` **and** `effort ∈ {XS, S}`.
Rollups form per dimension when ≥4 eligible findings exist in it. P0/P1 are always
individual issues. INFO findings are never filed as issues.

## Prioritization narrative

The report's "recommended sequencing" should not be a severity sort. Order by:
1. P0s, immediately, with mitigations named.
2. Cheap P1s (effort ≤ S) — momentum and risk reduction.
3. The root-cause findings whose fix collapses many children.
4. Remaining P1s by risk.
5. P2 hotspot work aligned with planned feature work ("fix when touching").
Never recommend more than ~8 workstreams; an audit that recommends everything
recommends nothing.
