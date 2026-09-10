import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import fingerprint


def _finding(rule, severity="P2", path="src/a.py"):
    return fingerprint.new_finding(
        dimension="security", rule=rule, source="test", severity=severity,
        title=rule, description="d", locations=[{"path": path, "startLine": 1}])


def test_ids_stable_across_saves(tmp_path):
    fp = tmp_path / "findings.json"
    doc = {"schema": "1.0", "audit": {}, "findings": [_finding("x.one", "P3"),
                                                        _finding("x.two", "P1")]}
    fingerprint.save_findings(doc, fp)
    before = {f["fingerprint"]: f["id"] for f in json.loads(fp.read_text())["findings"]}

    doc = fingerprint.load_findings(fp)
    doc["findings"].append(_finding("x.zero", "P0"))
    fingerprint.save_findings(doc, fp)
    after = {f["fingerprint"]: f["id"] for f in json.loads(fp.read_text())["findings"]}

    for k, v in before.items():
        assert after[k] == v
    ids = set(after.values())
    assert len(ids) == 3


def test_new_id_exceeds_all_existing(tmp_path):
    fp = tmp_path / "findings.json"
    old = _finding("x.old")
    old["id"] = "CA-2025-0042"
    doc = {"schema": "1.0", "audit": {}, "findings": [old, _finding("x.new")]}
    fingerprint.save_findings(doc, fp)
    ids = {f["rule"]: f["id"] for f in json.loads(fp.read_text())["findings"]}
    assert ids["x.old"] == "CA-2025-0042"
    assert ids["x.new"].endswith("-0043")
