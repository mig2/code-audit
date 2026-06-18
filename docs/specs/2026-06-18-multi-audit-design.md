# Multi-audit support

Store each audit run in a timestamped directory, maintain a history manifest, auto-link baselines, and upgrade the dashboard to show trends across audits without manual flags.

## Motivation

Currently audits overwrite `.audit/`, losing prior results. Comparing audits requires manually passing `--history` and `--baseline` flags with paths to old audit directories. This makes it impractical to track a repo's health over time.

## Design

### 1. Timestamped audit directories

Each audit run stores its artifacts in `.audit/YYYYMMDDHHMM/` instead of flat in `.audit/`. The timestamp is generated at init time using local time.

```
.audit/
├── audit-history.json          # manifest (repo-level)
├── suppressions.json           # repo-level, not per-audit
├── 202606181200/
│   ├── repo-profile.json
│   ├── tool-report.json
│   ├── metrics.json
│   ├── raw/
│   ├── findings.json
│   ├── narrative.json
│   ├── baseline.json
│   ├── report.md
│   ├── report.html
│   ├── dashboard.html
│   └── issues-manifest.json
├── 202607011430/
│   └── ...
```

### 2. Audit history manifest (`.audit/audit-history.json`)

```json
{
  "repo": "owner/repo-name",
  "remote": "git@github.com:owner/repo.git",
  "audits": [
    {
      "id": "202606181200",
      "dir": "202606181200",
      "timestamp": "2026-06-18T12:00:00Z",
      "commit": "abc123def",
      "branch": "main",
      "tier": "standard",
      "baseline_from": null,
      "status": "complete"
    }
  ]
}
```

Fields:
- `id` / `dir`: the timestamped directory name
- `baseline_from`: the `id` of the previous audit used as baseline, or null for first run
- `status`: `in-progress`, `complete`, or `failed`

### 3. New script: `scripts/audit_history.py`

Three subcommands plus a migration helper:

**`init REPO_ROOT --out .audit`**
- Creates `.audit/YYYYMMDDHHMM/` directory
- Adds an entry to `audit-history.json` with `status: "in-progress"`
- Finds the most recent `complete` audit and sets `baseline_from`
- Prints the new audit dir path to stdout

**`register AUDIT_DIR`**
- Updates the manifest entry's `status` to `complete`
- Fills in `commit`, `branch`, `tier` from `repo-profile.json` and `narrative.json`

**`previous AUDIT_DIR`**
- Prints the path to the previous complete audit dir (or nothing if first run)
- Used by `baseline.py` and `render_dashboard.py` for auto-discovery

**`migrate .audit`**
- Moves existing flat `.audit/` contents into a timestamped subdirectory
- Derives timestamp from audit metadata or file mtime
- Creates `audit-history.json` with that single entry as `complete`
- Leaves `suppressions.json` in place at the `.audit/` level

### 4. Changes to existing scripts

**`baseline.py`**
- When no `--baseline` is given, call `audit_history.py previous` to find the prior audit dir and use its `findings.json` as baseline
- Explicit `--baseline` flag still works as an override

**`render_dashboard.py`**
- When no `--history` is given, read `audit-history.json` and use all `complete` audit dirs as history
- Explicit `--history` flag still works as an override

**`render_report.py`**
- No changes. Operates on a single audit dir, now `.audit/YYYYMMDDHHMM/`.

### 5. SKILL.md updates

- Phase 0: after `detect_repo.py`, call `audit_history.py init` and use the returned path as `AUDIT_DIR`
- Phase 4: note that baseline auto-links via the manifest; manual `--baseline` is optional override
- Phase 5: after rendering, call `audit_history.py register`
- Update workspace layout diagram to show timestamped structure

### 6. Dashboard

No changes to the dashboard template or JS. The existing history chart and filtering already handle multiple data points. The only change is that `render_dashboard.py` auto-populates history from the manifest instead of requiring `--history` flags.
