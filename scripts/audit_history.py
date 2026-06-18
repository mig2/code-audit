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
    p = Path(audit_root) / "audit-history.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"repo": "", "remote": "", "audits": []}


def save_history(history, audit_root):
    p = Path(audit_root) / "audit-history.json"
    p.write_text(json.dumps(history, indent=2) + "\n")


def init_audit(audit_root, repo="", remote=""):
    audit_root = Path(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    dir_name = now.strftime("%Y%m%d%H%M")
    audit_dir = audit_root / dir_name

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


def register_audit(audit_dir):
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


def previous_audit(audit_dir):
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
        return None

    baseline_id = entry.get("baseline_from")
    if baseline_id is None:
        return None

    # verify the referenced audit is complete
    baseline_entry = None
    for a in history["audits"]:
        if a["id"] == baseline_id:
            baseline_entry = a
            break
    if baseline_entry is None or baseline_entry.get("status") != "complete":
        return None

    prev_dir = audit_root / baseline_id
    if prev_dir.exists():
        return prev_dir
    return None
