# Issues

## Closed

### #1 — Clean up download artifacts and create repo structure
- **Labels:** cleanup, setup
- **Description:** The working directory contains download artifacts (`auditskill.zip`, `code-audit.skill`, `sample-dashboard.html`, `sample-report.html`) alongside the extracted skill in `code-audit/`. Move skill contents to repo root, delete artifacts, and `git init`.
- **Resolution:** Deleted artifacts, moved `code-audit/*` to root, initialized git repo.
- **Commit:** f822a3d
- **Closed:** 2026-06-18

### #2 — Add README
- **Labels:** documentation
- **Description:** The repo has no README. Add one covering usage, the pipeline phases, output layout, tiers, and compare mode.
- **Resolution:** Added `README.md` with usage, pipeline table, output tree, tier descriptions, and compare mode section.
- **Commit:** f396942
- **Closed:** 2026-06-18

### #3 — Add install script with git hash stamp
- **Labels:** setup, tooling
- **Description:** There is no way to install the skill from this repo into `~/.claude/skills/code-audit/`. Add an `install.sh` that copies skill files and stamps the installed copy with the git commit hash it was built from.
- **Resolution:** Added `install.sh` that copies SKILL.md, scripts/, references/, assets/ and writes the short hash to `.installed-from`.
- **Commit:** 73dcbcc
- **Closed:** 2026-06-18

## Open

### #4 — Multi-audit support: timestamped audit directories
- **Labels:** enhancement, multi-audit
- **Description:** Instead of overwriting `.audit/`, store each audit run in `.audit/YYYYMMDDHHMM/`. Repo-level files (`suppressions.json`) remain at `.audit/` root.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §1

### #5 — Multi-audit support: audit history manifest
- **Labels:** enhancement, multi-audit
- **Description:** Add `.audit/audit-history.json` to track all past audits for a repo. Schema includes id, timestamp, commit, branch, tier, baseline linkage, and status (in-progress/complete/failed).
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §2

### #6 — Multi-audit support: `audit_history.py` script
- **Labels:** enhancement, multi-audit
- **Description:** New script with subcommands: `init` (create timestamped dir, register in manifest, auto-link baseline), `register` (mark audit complete), `previous` (print path to prior audit dir). Drives the other multi-audit features.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §3

### #7 — Multi-audit support: baseline auto-linking
- **Labels:** enhancement, multi-audit
- **Description:** Update `baseline.py` to auto-discover the previous audit's `findings.json` via `audit_history.py previous` when no explicit `--baseline` flag is given. Manual override still works.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §4

### #8 — Multi-audit support: dashboard auto-history
- **Labels:** enhancement, multi-audit
- **Description:** Update `render_dashboard.py` to read `audit-history.json` and auto-populate the `--history` trend data from all complete audits. Manual `--history` flag still works as override.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §4

### #9 — Multi-audit support: SKILL.md pipeline updates
- **Labels:** documentation, multi-audit
- **Description:** Update SKILL.md to reflect the new pipeline: call `audit_history.py init` in Phase 0, auto-baseline in Phase 4, call `audit_history.py register` in Phase 5. Update workspace layout diagram.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §5

### #10 — Migration script for existing audits
- **Labels:** enhancement, multi-audit
- **Description:** Add a `migrate` subcommand to `audit_history.py` that moves existing flat `.audit/` contents into a timestamped subdirectory, derives timestamp from metadata or file mtime, and creates the initial `audit-history.json`.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §3
