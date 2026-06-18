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
