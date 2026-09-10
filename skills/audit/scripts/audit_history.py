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
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


# files that stay at audit root (not moved into timestamped dir)
_ROOT_FILES = {"audit-history.json", "suppressions.json"}

# files/dirs that are audit artifacts (should be moved)
_AUDIT_ARTIFACTS = {
    "findings.json", "narrative.json", "repo-profile.json", "tool-report.json",
    "metrics.json", "baseline.json", "issues-manifest.json",
    "report.md", "report.html", "dashboard.html", "review-progress.json", "raw",
}


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


def migrate_audit(audit_root):
    audit_root = Path(audit_root)

    if (audit_root / "audit-history.json").exists():
        print("already migrated (audit-history.json exists)")
        return

    if not (audit_root / "findings.json").exists():
        sys.exit(f"no findings.json in {audit_root} — nothing to migrate")

    # derive timestamp from metadata or file mtime
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
        if item.name in _AUDIT_ARTIFACTS:
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
            "timestamp": ts.isoformat(),
            "commit": profile.get("commit", ""),
            "branch": profile.get("branch", ""),
            "tier": narrative.get("tier", ""),
            "baseline_from": None,
            "status": "complete",
        }],
    }
    save_history(history, audit_root)
    print(f"migrated to {ts_dir} — manifest created")


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
