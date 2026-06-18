import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_history


def test_load_history_no_file(tmp_audit):
    h = audit_history.load_history(tmp_audit)
    assert h["audits"] == []
    assert "repo" in h


def test_load_history_existing(tmp_audit):
    manifest = {"repo": "test", "remote": "git@x", "audits": [
        {"id": "202606181200", "status": "complete"}
    ]}
    (tmp_audit / "audit-history.json").write_text(json.dumps(manifest))
    h = audit_history.load_history(tmp_audit)
    assert len(h["audits"]) == 1
    assert h["audits"][0]["id"] == "202606181200"


def test_save_history(tmp_audit):
    h = {"repo": "test", "remote": "", "audits": []}
    audit_history.save_history(h, tmp_audit)
    written = json.loads((tmp_audit / "audit-history.json").read_text())
    assert written == h
