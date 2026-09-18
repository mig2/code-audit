# Report — calibration.json schema, structure, tone

You write `calibration.json`; `scripts/render_calibration.py` renders `calibration.md`
and `calibration.html` (same template as the audit report) and appends a signals appendix
automatically. Do not hand-write the markdown.

## calibration.json

```jsonc
{
  "title": "Calibration of <repo> — 2026-09",
  "audit_dir": ".audit/202609101930",       // the run whose metrics/findings you used
  "purpose": "One paragraph: what this software is for, who uses it, what is at stake (data, money, users, uptime). Confirmed with the user in Phase 1.",
  "summary": "2–4 paragraphs, markdown. Lead with the headline: proportionate or not, and the required-vs-evident gap in one sentence. Then the two or three facts that most determine it.",
  "areas": [
    {
      "area": "abstraction",                 // abstraction | configurability | error-handling | testing | tooling-ci | dependencies | documentation | operability
      "verdict": "over-built",               // over-built | fitted | under-built
      "confidence": "high",                  // high | medium | low
      "evidence": [
        "src/core/repository.py:12 — `AbstractRepository` has one implementation (`SqliteRepository`)",
        "src/di/container.py:1 — DI container wiring 6 singletons in a single-process CLI"
      ],
      "note": "markdown — why this verdict, relative to the purpose"
    }
    // one entry per applicable area; operability only when is_service
  ],
  "required_level": {
    "level": "L2",
    "confidence": "medium",
    "drivers": ["Persistent state with migrations", "External users via the HTTP API", "No money or regulated data"],
    "note": "markdown — the least experienced person who could safely change this next month, and why"
  },
  "evident_level": {
    "level": "L1",
    "range": "L1–L2",                        // optional; use when the evidence spans rungs
    "confidence": "medium",
    "signatures": ["Consistent module layout (L2)", "Tests assert on mock calls, not outcomes (L1)", "Copy-paste family across three handlers (L1)"],
    "note": "markdown — what the code reveals about how it was built; multi-author or multi-era notes go here"
  },
  "gap": {
    "direction": "under-owned",              // under-owned (required > evident) | over-built (evident/structure > required) | matched | mixed
    "summary": "markdown — what the gap means in practice for this owner",
    "risks": ["The migration path is untested; a schema change could lose data", "…"],
    "plan": [
      { "step": "Add outcome-asserting tests around `apply_discount` and the date math in `billing/period.py`", "why": "These are the bug-shaped paths and currently have mock-only tests", "effort": "M" },
      { "step": "Remove `AbstractRepository`; call `SqliteRepository` directly", "why": "One implementation; the layer costs reading time and buys nothing", "effort": "S" }
    ]
  },
  "next_level": {                           // always include: the most useful section for the owner
    "level": "L4",                         // the rung above evident_level
    "differences": [                       // 3–6, each "what the next rung would have done here" with evidence
      "Failure modes named before the incident: every hardening traces to a dated outage (#303, #444, #475); L4 writes timeout enforcement on the day the scheduler is introduced",
      "…"
    ],
    "cheapest_step": "the one concrete step that moves the codebase furthest toward that rung per unit of effort"
  },
  "strengths": ["markdown bullets — what is genuinely well done; be specific"],
  "caveats": "markdown — single author / short history / generated-heavy / sample size; anything that bounds confidence"
}
```

`next_level` answers the question every owner asks first — "what would have made it the next rung?" — so
write it even when the levels match. Frame each difference as anticipating vs. reacting, what is
*absent*, or onboardable-without-a-conversation (see `ladder.md` § Reading the rung above). It is
about the code, not the person, like everything else here.

Levels are the codes `L0`–`L4`; the renderer expands them to their labels. Effort uses
the audit scale (S < half a day, M 1–3 days, L a week or more).

## Rendered structure (fixed)

1. Title line: date · audit dir · **Required Lx / Evident Ly**
2. Purpose
3. Summary
4. Proportionality by area — table, then one block per area with note + evidence
5. Required owner level — level, drivers, note
6. Evident author level — level/range, signatures, note
7. What L<n+1> would look like — differences, cheapest step (when `next_level` is present)
8. Gap — direction, summary, risks, plan table
9. Strengths
10. Caveats
11. Signals appendix (auto)

## Tone rules

- **Describe the code, not the person.** "The code exhibits…", "the tests assert…",
  never "the author doesn't know…". Owners and authors read this.
- **L0 is respected.** If working software was built by a non-engineer with an AI, say
  what was achieved first. The gap plan is a support plan, not a remediation list.
- **Lead with what matters.** Three plan steps that reduce risk beat twelve that improve
  hygiene. Order the plan by risk reduction per effort.
- **Waste is a finding.** When structure exceeds need, name what to remove and what it
  costs to keep. Do not soften "over-built" into "thorough".
- **Evidence or silence.** Every verdict cites locations. A hunch you cannot point at goes
  in `caveats` as a question, not in a verdict.
- **Confidence is real.** Short history, one author, heavy generation, or a small manual
  sample cap confidence at medium. Say which.
- Prose in `summary`, `note`, `gap.summary`; bullets only in the list fields. The renderer
  builds the tables.
