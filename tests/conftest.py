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
