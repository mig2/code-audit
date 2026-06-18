# Multi-Audit Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store each audit in a timestamped directory, maintain a history manifest, auto-link baselines, and auto-populate dashboard history.

**Architecture:** A new `scripts/audit_history.py` owns the manifest and timestamped directory lifecycle. Existing scripts (`baseline.py`, `render_dashboard.py`) gain auto-discovery by importing a shared `load_history()` function from `audit_history.py`. SKILL.md is updated to use the new commands.

**Tech Stack:** Python 3, stdlib only (json, argparse, pathlib, datetime, shutil)

**Issues:** #4, #5, #6, #7, #8, #9, #10 in `issues.md`

---

## File Map

- **Create:** `scripts/audit_history.py` — manifest management (init, register, previous, migrate)
- **Create:** `tests/test_audit_history.py` — tests for audit_history.py
- **Create:** `tests/test_baseline_autolink.py` — tests for baseline auto-discovery
- **Create:** `tests/test_dashboard_autohistory.py` — tests for dashboard auto-history
- **Modify:** `scripts/baseline.py:22-32` — `find_baseline()` to try manifest before file-path fallbacks
- **Modify:** `scripts/render_dashboard.py:60-98` — `main()` to auto-populate history from manifest
- **Modify:** `SKILL.md:56-187` — pipeline instructions and workspace layout

---

### Task 1: Scaffold test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create empty test package**

```python
# tests/__init__.py
# (empty)
```

- [ ] **Step 2: Create conftest with shared fixtures**

```python
# tests/conftest.py
import json
import shutil
from pathlib import Path
from datetime import datetime

import pytest


@pytest.fixture
def tmp_audit(tmp_path):
    """A .audit/ directory inside a fake repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    audit = repo / ".audit"
    audit.mkdir()
    return audit


@pytest.fixture
def sample_findings():
    """Minimal valid findings.json content."""
    return {
        "schema": "1.0",
        "audit": {"repo": "/tmp/repo", "commit": "abc123", "branch": "main"},
        "findings": [
            {
                "id": "CA-2026-0001",
                "fingerprint": "sha256:aaa111",
                "dimension": "security",
                "rule": "bandit.B101",
                "source": "bandit",
                "severity": "P2",
                "confidence": "high",
                "effort": "S",
                "title": "Use of assert",
                "description": "assert used in production code",
                "recommendation": "Use proper validation",
                "locations": [{"path": "src/main.py", "startLine": 10}],
                "language": "python",
                "status": "new",
                "suppressReason": None,
                "relatedFingerprints": [],
                "tracker": {"url": None, "id": None},
            }
        ],
    }


@pytest.fixture
def sample_narrative():
    """Minimal narrative.json content."""
    return {
        "title": "Test Audit",
        "tier": "standard",
        "executive_summary": "Test summary.",
        "scorecard": [
            {"dimension": "security", "grade": "B", "assessed": True, "summary": "OK"}
        ],
    }


@pytest.fixture
def sample_profile():
    """Minimal repo-profile.json content."""
    return {
        "repo": "/tmp/repo",
        "remote": "git@github.com:owner/repo.git",
        "commit": "abc123def456",
        "branch": "main",
        "languages": [{"language": "python", "loc": 5000}],
    }


def write_audit(audit_dir, findings, narrative=None, profile=None):
    """Helper to write a complete audit directory."""
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "findings.json").write_text(json.dumps(findings, indent=2))
    if narrative:
        (audit_dir / "narrative.json").write_text(json.dumps(narrative, indent=2))
    if profile:
        (audit_dir / "repo-profile.json").write_text(json.dumps(profile, indent=2))
```

- [ ] **Step 3: Verify pytest discovers the fixtures**

Run: `cd /Users/mattgreenwood/Code/audit && python3 -m pytest tests/ --collect-only`
Expected: "no tests ran" (but no errors)

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "Add test infrastructure with shared fixtures"
```

---

### Task 2: `audit_history.py` — manifest loading and saving

**Files:**
- Create: `scripts/audit_history.py`
- Create: `tests/test_audit_history.py`

- [ ] **Step 1: Write failing tests for load/save manifest**

```python
# tests/test_audit_history.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_history


def test_load_history_no_file(tmp_audit):
    """Loading from a dir with no manifest returns empty structure."""
    h = audit_history.load_history(tmp_audit)
    assert h["audits"] == []
    assert "repo" in h


def test_load_history_existing(tmp_audit):
    """Loading reads an existing manifest."""
    manifest = {"repo": "test", "remote": "git@x", "audits": [
        {"id": "202606181200", "status": "complete"}
    ]}
    (tmp_audit / "audit-history.json").write_text(json.dumps(manifest))
    h = audit_history.load_history(tmp_audit)
    assert len(h["audits"]) == 1
    assert h["audits"][0]["id"] == "202606181200"


def test_save_history(tmp_audit):
    """Saving writes valid JSON."""
    h = {"repo": "test", "remote": "", "audits": []}
    audit_history.save_history(h, tmp_audit)
    written = json.loads((tmp_audit / "audit-history.json").read_text())
    assert written == h
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: FAIL — `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Implement load/save**

```python
#!/usr/bin/env python3
"""Audit history: manage timestamped audit directories and manifest.

Subcommands:
    init REPO_ROOT --out .audit     Create new timestamped audit dir
    register AUDIT_DIR              Mark audit complete in manifest
    previous AUDIT_DIR              Print path to previous complete audit
    migrate AUDIT_DIR               Move flat .audit/ into timestamped layout
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_history(audit_root):
    """Load audit-history.json from audit_root, or return empty structure."""
    p = Path(audit_root) / "audit-history.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"repo": "", "remote": "", "audits": []}


def save_history(history, audit_root):
    """Write audit-history.json to audit_root."""
    p = Path(audit_root) / "audit-history.json"
    p.write_text(json.dumps(history, indent=2) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_history.py tests/test_audit_history.py
git commit -m "Add audit_history.py with manifest load/save"
```

---

### Task 3: `audit_history.py init` subcommand

**Files:**
- Modify: `scripts/audit_history.py`
- Modify: `tests/test_audit_history.py`

- [ ] **Step 1: Write failing tests for init**

Append to `tests/test_audit_history.py`:

```python
def test_init_creates_timestamped_dir(tmp_audit):
    """init creates a YYYYMMDDHHMM directory and returns its path."""
    result = audit_history.init_audit(tmp_audit, repo="/tmp/repo", remote="git@x")
    assert result.exists()
    assert result.parent == tmp_audit
    # dir name is 12 digits
    assert len(result.name) == 12
    assert result.name.isdigit()


def test_init_adds_manifest_entry(tmp_audit):
    """init adds an in-progress entry to the manifest."""
    audit_history.init_audit(tmp_audit, repo="/tmp/repo", remote="git@x")
    h = audit_history.load_history(tmp_audit)
    assert len(h["audits"]) == 1
    assert h["audits"][0]["status"] == "in-progress"
    assert h["repo"] == "/tmp/repo"
    assert h["remote"] == "git@x"


def test_init_links_baseline_to_previous(tmp_audit):
    """init sets baseline_from to the last complete audit."""
    # create a prior complete audit
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None}
    ]}
    audit_history.save_history(h, tmp_audit)
    (tmp_audit / "202601011000").mkdir()

    result = audit_history.init_audit(tmp_audit, repo="r", remote="")
    h2 = audit_history.load_history(tmp_audit)
    new_entry = h2["audits"][-1]
    assert new_entry["baseline_from"] == "202601011000"


def test_init_no_baseline_on_first_run(tmp_audit):
    """First audit has baseline_from=None."""
    audit_history.init_audit(tmp_audit, repo="r", remote="")
    h = audit_history.load_history(tmp_audit)
    assert h["audits"][0]["baseline_from"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_history.py::test_init_creates_timestamped_dir -v`
Expected: FAIL — `AttributeError: module has no attribute 'init_audit'`

- [ ] **Step 3: Implement init_audit**

Add to `scripts/audit_history.py`:

```python
def init_audit(audit_root, repo="", remote=""):
    """Create a timestamped audit directory and register it in the manifest.

    Returns the Path to the new audit directory.
    """
    audit_root = Path(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    dir_name = now.strftime("%Y%m%d%H%M")
    audit_dir = audit_root / dir_name

    # handle rare collision (two inits in same minute)
    if audit_dir.exists():
        suffix = 1
        while (audit_root / f"{dir_name}_{suffix}").exists():
            suffix += 1
        dir_name = f"{dir_name}_{suffix}"
        audit_dir = audit_root / dir_name

    audit_dir.mkdir()

    history = load_history(audit_root)
    history["repo"] = repo or history.get("repo", "")
    history["remote"] = remote or history.get("remote", "")

    # find most recent complete audit for baseline linking
    complete = [a for a in history["audits"] if a["status"] == "complete"]
    baseline_from = complete[-1]["id"] if complete else None

    entry = {
        "id": dir_name,
        "dir": dir_name,
        "timestamp": now.astimezone(timezone.utc).isoformat(),
        "commit": "",
        "branch": "",
        "tier": "",
        "baseline_from": baseline_from,
        "status": "in-progress",
    }
    history["audits"].append(entry)
    save_history(history, audit_root)

    return audit_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_history.py tests/test_audit_history.py
git commit -m "Add audit_history init subcommand with baseline auto-linking"
```

---

### Task 4: `audit_history.py register` subcommand

**Files:**
- Modify: `scripts/audit_history.py`
- Modify: `tests/test_audit_history.py`

- [ ] **Step 1: Write failing tests for register**

Append to `tests/test_audit_history.py`:

```python
from conftest import write_audit


def test_register_marks_complete(tmp_audit, sample_findings, sample_narrative, sample_profile):
    """register sets status to complete and fills metadata."""
    audit_dir = audit_history.init_audit(tmp_audit, repo="/tmp/repo", remote="git@x")
    write_audit(audit_dir, sample_findings, sample_narrative, sample_profile)

    audit_history.register_audit(audit_dir)

    h = audit_history.load_history(tmp_audit)
    entry = h["audits"][-1]
    assert entry["status"] == "complete"
    assert entry["commit"] == "abc123def456"
    assert entry["branch"] == "main"
    assert entry["tier"] == "standard"


def test_register_missing_dir_fails(tmp_audit):
    """register raises if the audit dir doesn't exist in manifest."""
    with pytest.raises(SystemExit):
        audit_history.register_audit(tmp_audit / "nonexistent")
```

Add `import pytest` at the top of the test file if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_history.py::test_register_marks_complete -v`
Expected: FAIL — `AttributeError: module has no attribute 'register_audit'`

- [ ] **Step 3: Implement register_audit**

Add to `scripts/audit_history.py`:

```python
def register_audit(audit_dir):
    """Mark an audit as complete, filling metadata from its artifacts."""
    audit_dir = Path(audit_dir)
    audit_root = audit_dir.parent
    dir_name = audit_dir.name

    history = load_history(audit_root)
    entry = None
    for a in history["audits"]:
        if a["id"] == dir_name:
            entry = a
            break
    if entry is None:
        sys.exit(f"audit {dir_name} not found in {audit_root / 'audit-history.json'}")

    # fill metadata from artifacts
    profile_p = audit_dir / "repo-profile.json"
    if profile_p.exists():
        profile = json.loads(profile_p.read_text())
        entry["commit"] = profile.get("commit", "")
        entry["branch"] = profile.get("branch", "")

    narrative_p = audit_dir / "narrative.json"
    if narrative_p.exists():
        narrative = json.loads(narrative_p.read_text())
        entry["tier"] = narrative.get("tier", "")

    entry["status"] = "complete"
    save_history(history, audit_root)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_history.py tests/test_audit_history.py
git commit -m "Add audit_history register subcommand"
```

---

### Task 5: `audit_history.py previous` subcommand

**Files:**
- Modify: `scripts/audit_history.py`
- Modify: `tests/test_audit_history.py`

- [ ] **Step 1: Write failing tests for previous**

Append to `tests/test_audit_history.py`:

```python
def test_previous_returns_prior_audit(tmp_audit, sample_findings):
    """previous returns the path to the prior complete audit."""
    # set up two audits: first complete, second in-progress
    first = tmp_audit / "202601011000"
    first.mkdir()
    write_audit(first, sample_findings)
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "in-progress",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    (tmp_audit / "202602011000").mkdir()
    audit_history.save_history(h, tmp_audit)

    result = audit_history.previous_audit(tmp_audit / "202602011000")
    assert result == first


def test_previous_returns_none_for_first(tmp_audit):
    """previous returns None when there's no prior audit."""
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "in-progress",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
    ]}
    (tmp_audit / "202601011000").mkdir()
    audit_history.save_history(h, tmp_audit)

    result = audit_history.previous_audit(tmp_audit / "202601011000")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_history.py::test_previous_returns_prior_audit -v`
Expected: FAIL — `AttributeError: module has no attribute 'previous_audit'`

- [ ] **Step 3: Implement previous_audit**

Add to `scripts/audit_history.py`:

```python
def previous_audit(audit_dir):
    """Return the Path to the previous complete audit dir, or None."""
    audit_dir = Path(audit_dir)
    audit_root = audit_dir.parent
    dir_name = audit_dir.name

    history = load_history(audit_root)

    # find this audit's entry
    entry = None
    for a in history["audits"]:
        if a["id"] == dir_name:
            entry = a
            break
    if entry is None:
        return None

    baseline_id = entry.get("baseline_from")
    if baseline_id is None:
        return None

    prev_dir = audit_root / baseline_id
    if prev_dir.exists():
        return prev_dir
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: 11 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_history.py tests/test_audit_history.py
git commit -m "Add audit_history previous subcommand"
```

---

### Task 6: `audit_history.py` CLI (argparse main)

**Files:**
- Modify: `scripts/audit_history.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_audit_history.py`:

```python
import subprocess


def test_cli_init(tmp_audit):
    """CLI init prints the new audit dir path."""
    repo = tmp_audit.parent
    result = subprocess.run(
        ["python3", "scripts/audit_history.py", "init", str(repo), "--out", str(tmp_audit)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent
    )
    assert result.returncode == 0
    output_path = result.stdout.strip()
    assert Path(output_path).exists()


def test_cli_previous_no_prior(tmp_audit):
    """CLI previous prints nothing when no prior audit exists."""
    # init a first audit
    audit_dir = audit_history.init_audit(tmp_audit, repo="r", remote="")
    result = subprocess.run(
        ["python3", "scripts/audit_history.py", "previous", str(audit_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_history.py::test_cli_init -v`
Expected: FAIL — no `main()` or argparse

- [ ] **Step 3: Implement CLI main**

Add to `scripts/audit_history.py`:

```python
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create new timestamped audit directory")
    p_init.add_argument("repo_root", help="Path to the repository being audited")
    p_init.add_argument("--out", required=True, help="Audit root directory (e.g. .audit)")

    p_reg = sub.add_parser("register", help="Mark audit as complete")
    p_reg.add_argument("audit_dir", help="Path to the timestamped audit directory")

    p_prev = sub.add_parser("previous", help="Print path to previous complete audit")
    p_prev.add_argument("audit_dir", help="Path to the current audit directory")

    p_mig = sub.add_parser("migrate", help="Migrate flat .audit/ to timestamped layout")
    p_mig.add_argument("audit_dir", help="Path to .audit/ directory to migrate")

    args = ap.parse_args()

    if args.cmd == "init":
        # try to read repo info
        repo_root = Path(args.repo_root)
        remote = ""
        try:
            import subprocess as sp
            r = sp.run(["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                       capture_output=True, text=True)
            if r.returncode == 0:
                remote = r.stdout.strip()
        except FileNotFoundError:
            pass
        audit_dir = init_audit(Path(args.out), repo=str(repo_root), remote=remote)
        print(audit_dir)

    elif args.cmd == "register":
        register_audit(Path(args.audit_dir))
        print(f"registered {Path(args.audit_dir).name} as complete")

    elif args.cmd == "previous":
        prev = previous_audit(Path(args.audit_dir))
        if prev:
            print(prev)

    elif args.cmd == "migrate":
        migrate_audit(Path(args.audit_dir))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: 13 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_history.py tests/test_audit_history.py
git commit -m "Add audit_history CLI with argparse"
```

---

### Task 7: `audit_history.py migrate` subcommand

**Files:**
- Modify: `scripts/audit_history.py`
- Modify: `tests/test_audit_history.py`

- [ ] **Step 1: Write failing tests for migrate**

Append to `tests/test_audit_history.py`:

```python
import os


def test_migrate_moves_flat_audit(tmp_audit, sample_findings, sample_narrative, sample_profile):
    """migrate moves flat .audit/ contents into a timestamped subdir."""
    # write flat audit files
    write_audit(tmp_audit, sample_findings, sample_narrative, sample_profile)

    audit_history.migrate_audit(tmp_audit)

    # flat files should be gone
    assert not (tmp_audit / "findings.json").exists()
    # manifest should exist
    h = audit_history.load_history(tmp_audit)
    assert len(h["audits"]) == 1
    assert h["audits"][0]["status"] == "complete"
    # files should be in timestamped dir
    ts_dir = tmp_audit / h["audits"][0]["dir"]
    assert (ts_dir / "findings.json").exists()
    assert (ts_dir / "narrative.json").exists()
    assert (ts_dir / "repo-profile.json").exists()


def test_migrate_preserves_suppressions(tmp_audit, sample_findings):
    """migrate leaves suppressions.json at the audit root level."""
    write_audit(tmp_audit, sample_findings)
    supp = {"suppress": [{"fingerprint": "sha256:aaa111", "reason": "accepted"}]}
    (tmp_audit / "suppressions.json").write_text(json.dumps(supp))

    audit_history.migrate_audit(tmp_audit)

    assert (tmp_audit / "suppressions.json").exists()
    h = audit_history.load_history(tmp_audit)
    ts_dir = tmp_audit / h["audits"][0]["dir"]
    assert not (ts_dir / "suppressions.json").exists()


def test_migrate_skips_if_already_migrated(tmp_audit):
    """migrate exits cleanly if audit-history.json already exists."""
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None}
    ]}
    audit_history.save_history(h, tmp_audit)
    (tmp_audit / "202601011000").mkdir()

    # should not raise
    audit_history.migrate_audit(tmp_audit)
    # manifest unchanged
    h2 = audit_history.load_history(tmp_audit)
    assert len(h2["audits"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_history.py::test_migrate_moves_flat_audit -v`
Expected: FAIL — `AttributeError: module has no attribute 'migrate_audit'`

- [ ] **Step 3: Implement migrate_audit**

Add to `scripts/audit_history.py`:

```python
import shutil
import os


# files that stay at audit root (not moved into timestamped dir)
_ROOT_FILES = {"audit-history.json", "suppressions.json"}

# files/dirs that are audit artifacts (should be moved)
_AUDIT_ARTIFACTS = {
    "findings.json", "narrative.json", "repo-profile.json", "tool-report.json",
    "metrics.json", "baseline.json", "issues-manifest.json",
    "report.md", "report.html", "dashboard.html", "review-progress.json", "raw",
}


def migrate_audit(audit_root):
    """Migrate a flat .audit/ directory to timestamped layout.

    Moves audit artifacts into a timestamped subdirectory and creates
    the audit-history.json manifest. Leaves suppressions.json in place.
    """
    audit_root = Path(audit_root)

    # skip if already migrated
    if (audit_root / "audit-history.json").exists():
        print("already migrated (audit-history.json exists)")
        return

    # check there's something to migrate
    if not (audit_root / "findings.json").exists():
        sys.exit(f"no findings.json in {audit_root} — nothing to migrate")

    # derive timestamp from narrative or findings metadata, fallback to file mtime
    ts = None
    for meta_file in ("narrative.json", "findings.json"):
        p = audit_root / meta_file
        if p.exists():
            doc = json.loads(p.read_text())
            date_str = doc.get("audit", {}).get("date") or doc.get("date")
            if date_str:
                try:
                    ts = datetime.fromisoformat(date_str)
                except (ValueError, TypeError):
                    pass
            if ts is None:
                ts = datetime.fromtimestamp(p.stat().st_mtime)
            break
    if ts is None:
        ts = datetime.now()

    dir_name = ts.strftime("%Y%m%d%H%M")
    ts_dir = audit_root / dir_name
    ts_dir.mkdir(exist_ok=True)

    # move audit artifacts
    for item in list(audit_root.iterdir()):
        if item.name in _ROOT_FILES or item.name == dir_name:
            continue
        if item.name in _AUDIT_ARTIFACTS or item.name not in _ROOT_FILES:
            # skip other timestamped dirs (digits-only names)
            if item.is_dir() and item.name.isdigit() and len(item.name) == 12:
                continue
            shutil.move(str(item), str(ts_dir / item.name))

    # read metadata for manifest entry
    profile = {}
    narrative = {}
    profile_p = ts_dir / "repo-profile.json"
    if profile_p.exists():
        profile = json.loads(profile_p.read_text())
    narrative_p = ts_dir / "narrative.json"
    if narrative_p.exists():
        narrative = json.loads(narrative_p.read_text())

    history = {
        "repo": profile.get("repo", ""),
        "remote": profile.get("remote", ""),
        "audits": [{
            "id": dir_name,
            "dir": dir_name,
            "timestamp": ts.astimezone(timezone.utc).isoformat() if ts.tzinfo else ts.isoformat(),
            "commit": profile.get("commit", ""),
            "branch": profile.get("branch", ""),
            "tier": narrative.get("tier", ""),
            "baseline_from": None,
            "status": "complete",
        }],
    }
    save_history(history, audit_root)
    print(f"migrated to {ts_dir} — manifest created")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_history.py -v`
Expected: 16 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_history.py tests/test_audit_history.py
git commit -m "Add audit_history migrate subcommand"
```

---

### Task 8: Update `baseline.py` with auto-discovery

**Files:**
- Modify: `scripts/baseline.py:22-32`
- Create: `tests/test_baseline_autolink.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_baseline_autolink.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_history
import baseline
from conftest import write_audit


def test_find_baseline_uses_manifest(tmp_audit, sample_findings):
    """find_baseline discovers prior audit via manifest when no explicit baseline given."""
    # set up a complete prior audit
    prior = tmp_audit / "202601011000"
    write_audit(prior, sample_findings)

    # set up manifest with prior complete and current in-progress
    current = tmp_audit / "202602011000"
    current.mkdir()
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "in-progress",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    audit_history.save_history(h, tmp_audit)

    # write findings in current dir
    (current / "findings.json").write_text(json.dumps(sample_findings))

    result = baseline.find_baseline(str(current / "findings.json"), None)
    assert result is not None
    assert "202601011000" in str(result)


def test_find_baseline_explicit_overrides_manifest(tmp_audit, sample_findings):
    """Explicit --baseline flag takes precedence over manifest."""
    explicit = tmp_audit / "explicit-baseline.json"
    explicit.write_text(json.dumps({"findings": []}))
    result = baseline.find_baseline(str(tmp_audit / "findings.json"), str(explicit))
    assert result == explicit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_baseline_autolink.py -v`
Expected: FAIL — `find_baseline` doesn't check the manifest

- [ ] **Step 3: Update find_baseline in baseline.py**

Replace the `find_baseline` function in `scripts/baseline.py`:

```python
def find_baseline(findings_path, explicit):
    if explicit:
        return Path(explicit)

    # try manifest-based auto-discovery
    findings_dir = Path(findings_path).parent
    try:
        from audit_history import previous_audit
        prev = previous_audit(findings_dir)
        if prev and (prev / "findings.json").exists():
            return prev / "findings.json"
    except (ImportError, Exception):
        pass

    # fallback to legacy file-path search
    doc = json.loads(Path(findings_path).read_text())
    repo = Path(doc.get("audit", {}).get("repo", "."))
    for cand in (repo / ".audit-baseline.json",
                 Path(findings_path).parent / "baseline.json"):
        if cand.exists():
            return cand
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_baseline_autolink.py tests/test_audit_history.py -v`
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/baseline.py tests/test_baseline_autolink.py
git commit -m "Auto-discover baseline from audit history manifest"
```

---

### Task 9: Update `render_dashboard.py` with auto-history

**Files:**
- Modify: `scripts/render_dashboard.py:60-98`
- Create: `tests/test_dashboard_autohistory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard_autohistory.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_history
import render_dashboard
from conftest import write_audit


def test_auto_history_from_manifest(tmp_audit, sample_findings, sample_profile):
    """Dashboard auto-populates history from manifest when no --history flag."""
    # two complete audits
    for ts_id, fp in [("202601011000", "sha256:aaa111"), ("202602011000", "sha256:bbb222")]:
        findings = dict(sample_findings)
        findings["findings"] = [dict(sample_findings["findings"][0], fingerprint=fp)]
        d = tmp_audit / ts_id
        write_audit(d, findings, profile=sample_profile)

    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
        {"id": "202602011000", "dir": "202602011000", "status": "complete",
         "timestamp": "2026-02-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": "202601011000"},
    ]}
    audit_history.save_history(h, tmp_audit)

    history = render_dashboard.build_history_from_manifest(tmp_audit, "202602011000")
    assert len(history) == 2
    assert history[0]["label"] == "202601011000"


def test_auto_history_empty_when_single_audit(tmp_audit, sample_findings, sample_profile):
    """No history data when there's only one audit."""
    write_audit(tmp_audit / "202601011000", sample_findings, profile=sample_profile)
    h = {"repo": "r", "remote": "", "audits": [
        {"id": "202601011000", "dir": "202601011000", "status": "complete",
         "timestamp": "2026-01-01T10:00:00Z", "commit": "", "branch": "",
         "tier": "", "baseline_from": None},
    ]}
    audit_history.save_history(h, tmp_audit)

    history = render_dashboard.build_history_from_manifest(tmp_audit, "202601011000")
    assert len(history) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dashboard_autohistory.py -v`
Expected: FAIL — `AttributeError: module has no attribute 'build_history_from_manifest'`

- [ ] **Step 3: Add build_history_from_manifest and update main**

Add this function to `scripts/render_dashboard.py` (after the `slim` function):

```python
def build_history_from_manifest(audit_root, current_id):
    """Build history list from audit-history.json for the trend chart.

    Returns a list of {"label": ..., "counts": ...} dicts, including all
    complete audits. Returns empty list if fewer than 2 audits.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from audit_history import load_history  # noqa: E402

    audit_root = Path(audit_root)
    history_doc = load_history(audit_root)
    complete = [a for a in history_doc["audits"] if a["status"] == "complete"]
    if len(complete) < 2:
        return []

    result = []
    for a in complete:
        d = audit_root / a["dir"]
        findings, _, _ = collect(d)
        if findings:
            result.append({"label": a["id"][:12], "counts": severity_counts(findings)})
    return result
```

Update the `main()` function — replace the history-building block (lines ~76-83) with:

```python
    history = []
    if args.history:
        for hdir in args.history:
            hp = Path(hdir)
            hf, _, _ = collect(hp)
            history.append({"label": hp.name[:12],
                            "counts": severity_counts(hf)})
        history.append({"label": "current", "counts": severity_counts(findings)})
    else:
        # auto-discover from manifest
        audit_root = d.parent
        history = build_history_from_manifest(audit_root, d.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_dashboard_autohistory.py tests/test_audit_history.py -v`
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/render_dashboard.py tests/test_dashboard_autohistory.py
git commit -m "Auto-populate dashboard history from audit manifest"
```

---

### Task 10: Update SKILL.md

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Update Phase 0 to call audit_history init**

In the Phase 0 section, after the `detect_repo.py` command, add:

```bash
AUDIT_DIR=$(python3 scripts/audit_history.py init REPO --out .audit)
```

And update the text to note that `AUDIT_DIR` is now the timestamped directory returned by init.

- [ ] **Step 2: Update Phase 4 to note auto-linking**

Replace the baseline command example with:

```bash
python3 scripts/baseline.py AUDIT_DIR/findings.json --out AUDIT_DIR
```

And add a note: "Baseline auto-links to the previous audit via the manifest. Use `--baseline FILE` to override."

- [ ] **Step 3: Update Phase 5 to call audit_history register**

After the `render_dashboard.py` command, add:

```bash
python3 scripts/audit_history.py register AUDIT_DIR
```

- [ ] **Step 4: Update workspace layout**

Replace the workspace layout with:

```
.audit/                               # audit root; ensure gitignored
├── audit-history.json                # manifest of all audits
├── suppressions.json                 # repo-level suppressions
├── YYYYMMDDHHMM/                     # one per audit run
│   ├── repo-profile.json  tool-report.json  metrics.json
│   ├── raw/<tool>.{json,txt}
│   ├── findings.json                 # canonical
│   ├── narrative.json
│   ├── baseline.json  issues-manifest.json
│   ├── report.md  report.html  dashboard.html
│   └── review-progress.json          # deep-tier chunking state
```

- [ ] **Step 5: Update invocation docs**

Add `migrate` to the invocation section:

```
/code-audit migrate                   # move flat .audit/ to timestamped layout
```

- [ ] **Step 6: Commit**

```bash
git add SKILL.md
git commit -m "Update SKILL.md pipeline for multi-audit support"
```

---

### Task 11: Update issues.md — close all multi-audit issues

**Files:**
- Modify: `issues.md`

- [ ] **Step 1: Update each open issue (#4–#10) with resolution, commit hash, and closed date**

- [ ] **Step 2: Commit**

```bash
git add issues.md
git commit -m "Close multi-audit issues #4-#10"
```

---

## Self-Review

Checked against spec:
- **§1 Timestamped dirs:** Task 3 (init creates them), Task 7 (migrate converts flat)
- **§2 Manifest schema:** Task 2 (load/save), Task 3 (init populates), Task 4 (register completes)
- **§3 audit_history.py:** Tasks 2-7 cover init, register, previous, migrate, CLI
- **§4 baseline.py changes:** Task 8
- **§4 render_dashboard.py changes:** Task 9
- **§5 SKILL.md updates:** Task 10
- **§6 Dashboard:** No template changes needed (confirmed — existing JS handles history data)

No placeholders. All function names consistent across tasks (`init_audit`, `register_audit`, `previous_audit`, `migrate_audit`, `load_history`, `save_history`, `build_history_from_manifest`). All test code included.
