# The expertise ladder

One five-rung scale is used for both questions the skill answers — *what level should own
this codebase* and *what level evidently built it* — so the two are directly comparable.
The crosswalk columns exist so the reader can anchor each rung to a framework they already
know; they are approximate, and the signatures column is what you actually assess against.

| Level | Label | Dreyfus | SFIA responsibility | Typical industry ladder |
|---|---|---|---|---|
| **L0** | AI-assisted, not a software engineer | Novice | — | — (product owner, domain expert, hobbyist, founder) |
| **L1** | Junior engineer | Advanced beginner | 2 — Assist | Junior, SWE I, new grad |
| **L2** | Mid-level engineer | Competent | 3 — Apply | SWE II, Mid, "engineer" |
| **L3** | Senior engineer | Proficient | 4 — Enable | Senior |
| **L4** | Staff / principal engineer | Expert | 5–6 — Ensure, Initiate | Staff, Principal, Architect |

L0 is a first-class rung, not "below the ladder". A great deal of working software is now
built by people who are not engineers, directing an AI. That is a legitimate way to ship;
the skill's job is to tell such an owner honestly what they are holding and what support
it needs — never to talk down to them.

---

## Reading the two levels

### Required owner level — what the codebase *demands*

Assess from the repo's purpose (Phase 1 checkpoint) and `demand_drivers` in
`calibration-signals.json`. Ask: *what is the least experienced person who could safely
change this system next month?*

| Level | The codebase demands this when… |
|---|---|
| **L0** | Single-purpose tool or script; no concurrency; no auth, money, or personal data; no external users; failure is a re-run; the whole thing fits in one sitting's reading. An AI can regenerate it from the README. |
| **L1** | A small app or library with a few modules; tests exist to run before changing things; failures are visible and local; no security surface beyond "don't leak the API key"; one deployment target. |
| **L2** | Multiple components with real boundaries; a database or persistent state with migrations; some concurrency or async; external users or a public API; auth or personal data; needs someone who can reason about a change's blast radius before making it. |
| **L3** | Concurrency that can corrupt data if mishandled; money, health, legal or regulated data; uptime that someone is paged for; a security surface an attacker would target; a dependency graph where upgrades can break things silently; design decisions that need to be *not* made as much as made. |
| **L4** | Multi-service or multi-team system; migrations that cannot be rolled back; performance work with real cost consequences; backward-compatibility obligations to external consumers; the failure modes are system-level, not file-level. |

Weigh the *stakes* driver above all others: a 400-line script that moves money demands
L2–L3 ownership regardless of its size. Report the required level with the two or three
drivers that set it.

### Evident author level — what the code *reveals*

Assess from the manual sample (signals.md tells you what to read) plus the `indirection`,
`error_handling`, `testing`, `documentation`, `history` and `ai_assist_markers` blocks.
Ask: *what does the way this was built tell me about how the builder thinks?* — and mind
the guardrails at the end of this file.

| Level | Signatures — the code tends to show… |
|---|---|
| **L0** | Structure that follows *prompt* boundaries, not domain boundaries (one file per request that was made: `handle_upload.py`, `fix_login.py`, `utils2.py`); inconsistent idioms *within one file* (three ways to open a file); tests that restate the implementation line-for-line or assert on mocks only; generated-looking test names and Arrange/Act/Assert boilerplate on trivial tests; error handling that catches everything and logs "An error occurred"; dependencies added per feature, sometimes two for the same job; secrets or config inline; README written in a different register from the code (marketing prose vs. code, or a template README with the placeholders still in); commit messages that describe the prompt ("add the feature we discussed", "fix bug") or are AI co-authored on nearly every commit; no evidence anyone ran the code through a debugger or read a stack trace (bugs are fixed by adding another branch). Working software, and the author cannot say why the tricky part works. |
| **L1** | Idioms known but applied unevenly; copy-paste families that must be edited in sync; happy path solid, error paths thin; tests exist and are honest but brittle (order-dependent, real time/network); naming inconsistent across modules; one very large file that "grew"; over-commenting the obvious, under-commenting the odd; dependencies reasonable but unpinned or unmaintained. Learns by doing; errors of omission. |
| **L2** | Consistent conventions and a recognizable structure; module boundaries that mostly match the domain; error handling present and specific on the paths that matter; tests assert behavior, use fixtures sensibly, run fast; deliberate dependency choices; occasional *over*-abstraction from pattern-following (an interface because the book said so, a factory for one product) — errors of pattern rather than omission. |
| **L3** | Abstractions that match the domain and no more; trade-offs written down where they were made (ADRs, a "why" comment at the weird part); operability considered (structured logs, health checks, config from environment with sane defaults); tests aimed at the bug-shaped code; knows what *not* to build — simplicity where a junior would add a layer; migrations and compatibility handled. |
| **L4** | System-level thinking visible in file layout and interfaces; failure modes anticipated and named; simplicity that looks obvious in hindsight; upgrade and migration paths; the parts that will change are isolated from the parts that will not; documentation that a new senior can onboard from without a conversation. |

State the evident level as a **range with confidence** (e.g. "L1–L2, medium"). Codebases
with more than one author, or with a history that changes hands, get a range and a note on
which era the signatures come from (`history` block: authors, first-commit ratio).

---

## Reading the rung above

The report's `next_level` section answers "what would have made it L(n+1)?" — the first thing
an owner asks. Frame each difference with one of three lenses, and cite where the current
code shows the lower rung:

| From → To | The rung above tends to… |
|---|---|
| **L0 → L1** | Know *why* the tricky part works; structure by domain instead of by prompt; write tests that would fail if the behaviour changed; keep one way of doing each thing; own the dependencies it added. |
| **L1 → L2** | Apply idioms consistently across modules; handle the error path, not just the happy path; make tests independent of order, time and network; name things the same way everywhere; stop copy-pasting families and extract once. |
| **L2 → L3** | Build only the abstraction the domain needs (no interface with one implementation "for later"); write the trade-off down where it was made; consider operability as a design input; aim tests at the bug-shaped code; know what *not* to build. |
| **L3 → L4** | *Anticipate rather than react*: name the failure modes on the day the component is introduced, not after the incident. Isolate the parts that change from the parts that don't so growth stays safe by construction. Ship capability and its gate in the same change. Leave fewer moving parts doing the same job. Leave a map a new senior can onboard from without a conversation. |

Always end with the cheapest single step toward the next rung — one, not a list.

---

## Mapping signals to levels — reminders

- **AI co-authorship is evidence, not a verdict.** Seniors use AI assistants heavily; a
  high `ai_coauthor_commits` ratio combined with L2–L3 signatures means an engineer using a
  tool. It is the *combination* of AI markers with L0 structural signatures that indicates
  L0. Never derive L0 from `ai_assist_markers` alone.
- **Over-abstraction points *up* one rung, then *down*.** A single-implementation interface
  in a small repo is an L2 pattern-following tell, not an L3 signal — but it is also not
  L0/L1, who rarely build indirection at all.
- **Consistency beats correctness for level reading.** A uniformly mediocre style is a
  stronger L1/L2 signal than a mix of excellent and terrible, which suggests multiple
  authors, heavy generation, or copy-paste from varied sources.
- **Size is not level.** Big codebases can be L1-built; small ones can be L4-built. Read
  the shape, not the LOC.
- **Tests are the highest-signal area.** Whether tests exist says little; *what they
  assert* says almost everything. Read five test files before you decide anything.

---

## Guardrails

- The evident level describes **the code**, never the person. Write "the code exhibits
  L1–L2 signatures", not "the author is a junior". Owners read these reports.
- An L0 result for working software is a **success story with a support gap**. Say what
  was achieved, then what it needs. Lead the gap plan with the two or three things that
  would most reduce the owner's risk, not with everything that differs from L3 practice.
- When the required level is *below* the evident level, the finding is *waste*, not
  praise: sophistication the problem does not pay for is a maintenance cost the owner
  inherits. Name what to strip.
- Confidence must be honest. One author, short history, or a generated-heavy repo → at
  best medium confidence on the evident level.
