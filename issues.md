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

### #4 — Multi-audit support: timestamped audit directories
- **Labels:** enhancement, multi-audit
- **Description:** Instead of overwriting `.audit/`, store each audit run in `.audit/YYYYMMDDHHMM/`. Repo-level files (`suppressions.json`) remain at `.audit/` root.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §1
- **Resolution:** `init_audit()` creates timestamped directories; `migrate_audit()` converts existing flat layouts.
- **Commits:** 0fcfcc1, f1f6554
- **Closed:** 2026-06-18

### #5 — Multi-audit support: audit history manifest
- **Labels:** enhancement, multi-audit
- **Description:** Add `.audit/audit-history.json` to track all past audits for a repo. Schema includes id, timestamp, commit, branch, tier, baseline linkage, and status (in-progress/complete/failed).
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §2
- **Resolution:** `load_history()`/`save_history()` manage the manifest; `init_audit()` creates entries, `register_audit()` completes them.
- **Commits:** 92673ac, 0fcfcc1, 0b7fe68
- **Closed:** 2026-06-18

### #6 — Multi-audit support: `audit_history.py` script
- **Labels:** enhancement, multi-audit
- **Description:** New script with subcommands: `init` (create timestamped dir, register in manifest, auto-link baseline), `register` (mark audit complete), `previous` (print path to prior audit dir). Drives the other multi-audit features.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §3
- **Resolution:** Added `scripts/audit_history.py` with init, register, previous, migrate subcommands and CLI. 16 tests in `tests/test_audit_history.py`.
- **Commits:** 92673ac, 0fcfcc1, 0b7fe68, b81241f, 65d4da6, d19bc6d, f1f6554
- **Closed:** 2026-06-18

### #7 — Multi-audit support: baseline auto-linking
- **Labels:** enhancement, multi-audit
- **Description:** Update `baseline.py` to auto-discover the previous audit's `findings.json` via `audit_history.py previous` when no explicit `--baseline` flag is given. Manual override still works.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §4
- **Resolution:** Updated `find_baseline()` to call `previous_audit()` before legacy fallbacks. Tests in `tests/test_baseline_autolink.py`.
- **Commit:** 04d6e75
- **Closed:** 2026-06-18

### #8 — Multi-audit support: dashboard auto-history
- **Labels:** enhancement, multi-audit
- **Description:** Update `render_dashboard.py` to read `audit-history.json` and auto-populate the `--history` trend data from all complete audits. Manual `--history` flag still works as override.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §4
- **Resolution:** Added `build_history_from_manifest()` and updated `main()` to auto-populate when no `--history` flag. Tests in `tests/test_dashboard_autohistory.py`.
- **Commit:** e728e2b
- **Closed:** 2026-06-18

### #9 — Multi-audit support: SKILL.md pipeline updates
- **Labels:** documentation, multi-audit
- **Description:** Update SKILL.md to reflect the new pipeline: call `audit_history.py init` in Phase 0, auto-baseline in Phase 4, call `audit_history.py register` in Phase 5. Update workspace layout diagram.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §5
- **Resolution:** Updated Phase 0, Phase 4, Phase 5 instructions and workspace layout. Added migrate invocation.
- **Commit:** aa225d8
- **Closed:** 2026-06-18

### #10 — Migration script for existing audits
- **Labels:** enhancement, multi-audit
- **Description:** Add a `migrate` subcommand to `audit_history.py` that moves existing flat `.audit/` contents into a timestamped subdirectory, derives timestamp from metadata or file mtime, and creates the initial `audit-history.json`.
- **Spec:** `docs/specs/2026-06-18-multi-audit-design.md` §3
- **Resolution:** Added `migrate_audit()` and wired into CLI. Preserves `suppressions.json` at root. Tests in `tests/test_audit_history.py`.
- **Commit:** f1f6554
- **Closed:** 2026-06-18

### #11 — Install stamp records only a bare hash, so drift cannot be checked
- **Labels:** setup, tooling
- **Description:** `install.sh` wrote a short commit hash to `.installed-from`. That names a commit but not the repository it belongs to, and git hashes only resolve inside a known repo, so the source checkout could not be located and the installed payload could not be compared against it. Installing from a tree with uncommitted changes also recorded a commit that did not describe what was copied, with nothing to detect it.
- **Resolution:** The stamp is now JSON carrying `source_path`, `source_remote`, full `commit`, `branch`, `installed_at`, and `dirty`, and the installer warns when the source tree is dirty. The legacy bare-hash format stays readable; consumers report those installs as unverifiable rather than current.
- **Commit:** 78acbfa
- **Closed:** 2026-08-02

### #12 — `baseline.py --write-baseline` overwrites the previous audit's `findings.json` when auto-linked
- **Labels:** bug, multi-audit
- **Description:** `find_baseline()` returns the prior audit's `findings.json` via the manifest; `--write-baseline` then writes the trimmed snapshot to that same path (`baseline.py:138`), destroying the prior audit's data.
- **Resolution:** The snapshot is always written to `AUDIT_DIR/baseline.json`. Regression test asserts the prior audit's `findings.json` is byte-identical after a `--write-baseline` run.
- **Commit:** 058c8dd
- **Closed:** 2026-09-10

### #13 — OSV findings can never reach P0: CVSS vector string is parsed as a number
- **Labels:** bug
- **Description:** `normalize_findings.py:352` reads OSV `severity[].score` as a float, but it is a CVSS vector string (always contains `/`), so the expression is `0` and every OSV finding is P1.
- **Resolution:** Added `cvss3_base_score()` (CVSS 3.0/3.1 formula) and `osv_severity()` mapping ≥9→P0, 7–9→P1, 4–7→P2, <4→P3, falling back to the advisory's severity label; unknown stays P1. Parametrized tests against known vectors.
- **Commit:** 00fc500
- **Closed:** 2026-09-10

### #14 — `fingerprint.py` renumbers finding IDs on every save, so reports and issues cite unstable IDs
- **Labels:** bug
- **Description:** `save_findings()` reassigns `CA-YYYY-NNNN` across all findings on each save; `add-finding` shifts existing ids cited in reports and tracker issues.
- **Resolution:** Existing ids are preserved; new findings take the next number above the current maximum. Tests cover add-finding stability and cross-year continuation.
- **Commit:** e99d763
- **Closed:** 2026-09-10

### #15 — Phase 5 order: dashboard rendered before `register`, so the current audit is missing from its own trend chart
- **Labels:** bug, multi-audit, documentation
- **Description:** `build_history_from_manifest()` only includes `status == "complete"` audits; SKILL.md runs the dashboard before `register`, so the current audit is never in its own chart.
- **Resolution:** The current audit is included regardless of manifest status, so the documented order (dashboard, then register) now works. Test added.
- **Commit:** cf3f77b
- **Closed:** 2026-09-10

### #16 — Documented pipeline flags that do not exist or do not work
- **Labels:** bug, documentation
- **Description:** `--project NAME` is not implemented anywhere; `--path` is ignored by `run_scanners.py`; compare mode has no `comparison.html`/Outliers; `--rollup` has no HTML output.
- **Resolution:** `run_scanners.py` runs inside the profile's recorded `scope`; SKILL.md documents per-project audits via `--path`/`--out`. Compare mode emits Outliers and `comparison.html`; rollup emits `report.html`; `md_html` renders headings and tables.
- **Commit:** ae728e8
- **Closed:** 2026-09-10

### #19 — Reference and README drift
- **Labels:** documentation
- **Description:** README output tree is the old flat layout; `osv-scanner -r` syntax invalid in five lang files; GitLab epic ladder described but unimplemented; `check_tools --fast` undocumented; lang-file invocations diverge from `run_scanners` argv.
- **Resolution:** README, SKILL.md, issue-filing.md, portfolio.md, java.md, c-cpp.md corrected. The osv-scanner syntax turned out to be valid on v2.x and was left alone.
- **Commit:** 8e623ba
- **Closed:** 2026-09-10

### #20 — Fragility: install_tools.sh asset selection, render_report partial-metrics crash, skipped-tool inflation, dead code
- **Labels:** bug, tooling, cleanup
- **Description:** Release-asset grep can pick `.sig` files, no arm64 mapping, `curl` unchecked; `render_report` crashes on metrics without `source_loc`; `run_scanners` records all unavailable tools as skipped regardless of `--only`; assorted dead code.
- **Resolution:** All items addressed; exit-with-no-output is now recorded as a failed scan; `audit.date` stamped by normalize; tracked `.pyc` files untracked. Tests added.
- **Commit:** bf61a63
- **Closed:** 2026-09-10

### #17 — Scanner outputs written but never parsed; tools probed but never run
- **Labels:** enhancement, tooling
- **Description:** radon, cargo-deny, pmd output is written but has no parser. jscpd, vulture, knip, golangci-lint, clang-tidy, spotbugs, license tools and others are probed by `check_tools.py` but never run. Registry does not match the lang references.
- **Resolution:** Parsers for radon-cc, cargo-deny, pmd. jscpd, vulture, knip, golangci-lint, clang-tidy (with compile DB), license inventories, ruff format, radon mi, swift-format now run and normalize. Build-dependent tools marked manual in the registry; lang references match `run_scanners` argv. A test asserts every parser has a producer.
- **Commit:** 19736a5
- **Closed:** 2026-09-10

### #18 — `metrics.py` does not produce the inputs the dimension rubrics assume
- **Labels:** enhancement
- **Description:** No function-size distribution, regex-count "complexity", no duplication or license inventory, no coverage-by-area, cycle detection only for TS. Dead TODO loop and a redundant second file walk.
- **Resolution:** `metrics.json` gains `functions`, `complexity_source` (radon for Python), `duplication`, `licenses`, `coverage.by_area`, `import_cycles` (Python). Dead loop removed; single file walk. Report appendix and `dimensions.md` updated.
- **Commit:** 255bc39
- **Closed:** 2026-09-10

### #21 — Add tests for `normalize_findings` parsers, `metrics`, `render_report`, `detect_repo`
- **Labels:** enhancement, tooling
- **Description:** All 20 tests cover multi-audit plumbing; the 18 parsers, metrics, report rendering, repo detection, fingerprint id stability and compare/file-issues planning have none. Add fixture-based tests and a dev requirements file.
- **Resolution:** Fixtures for all 18 original parsers with mapping assertions; cap_floods, end-to-end normalize, detect_repo, file_issues dry-run tests; `requirements-dev.txt`. Suite grew from 20 to 115 tests across #12–#23.
- **Commit:** a40fc41
- **Closed:** 2026-09-10

### #23 — normalize_findings: govulncheck parser reads line-by-line so real output yields nothing; main() does not create --out
- **Labels:** bug
- **Description:** Real `govulncheck -json` output is pretty-printed multi-line JSON, so the line-oriented parser produced zero findings. `main()` failed with `FileNotFoundError` when `AUDIT_DIR` did not exist.
- **Resolution:** `iter_json_objects()` reads compact or pretty-printed streams; fixture converted to the real shape. `main()` creates the output directory.
- **Commit:** b95e7d8
- **Closed:** 2026-09-10

### #22 — Restructure into a `code` plugin bundle: `skills/audit` and `skills/calibration`
- **Labels:** enhancement, setup
- **Description:** Convert to a Claude Code plugin (`.claude-plugin/plugin.json`, `skills/<name>/SKILL.md`) so both skills are invoked as `/code:audit` and `/code:calibration`. Retire or wrap `install.sh`. Do after the audit fixes land.
- **Resolution:** Plugin manifest added; audit skill moved to `skills/audit/`; tests repointed; `install.sh` now symlinks `~/.claude/skills/code` to the clone (auto-loaded as `code@skills-dir`) and removes the legacy copy.
- **Commit:** 6a1e3fe
- **Closed:** 2026-09-10

### #24 — Add the `code:calibration` skill: proportionality and owner-expertise assessment
- **Labels:** enhancement
- **Description:** New skill at `skills/calibration/` producing per-area over-/under-built verdicts, a required-owner level and an evident-author level on an L0–L4 ladder (L0 = AI-assisted non-engineer), and a gap plan. Reuses an existing `.audit/` run; one stdlib signals script; references `ladder.md`, `signals.md`, `report.md`.
- **Resolution:** SKILL.md, three references, `calibration_signals.py` (15 signal blocks) and `render_calibration.py` added with 10 tests; README documents the skill; plugin lists both skills.
- **Commit:** 88a420e
- **Closed:** 2026-09-10

### #25 — `metrics.py` hangs: `git shortlog` reads stdin when not attached to a TTY
- **Labels:** bug
- **Description:** `git_authors()` ran `git shortlog -sn -- path` with no revision; without a TTY, shortlog reads the log from stdin and each hotspot lookup blocked for its full 60s timeout. Found during the calibration smoke run.
- **Resolution:** All git calls pass `HEAD` and `stdin=DEVNULL`; regression test with a never-closing stdin pipe.
- **Commit:** ddb2c0e
- **Closed:** 2026-09-10

## Open

(none)
