import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import normalize_findings as nf


@pytest.mark.parametrize("vector,score", [
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
    ("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H", 9.9),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H", 7.5),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N", 5.3),
    ("CVSS:3.0/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", 1.8),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0),
])
def test_cvss3_base_score(vector, score):
    assert nf.cvss3_base_score(vector) == score


def test_cvss3_unparseable():
    assert nf.cvss3_base_score("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H") is None
    assert nf.cvss3_base_score("") is None


@pytest.mark.parametrize("vuln,sev", [
    ({"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}]}, "P0"),
    ({"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H"}]}, "P1"),
    ({"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N"}]}, "P2"),
    ({"severity": [{"type": "CVSS_V3", "score": "CVSS:3.0/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N"}]}, "P3"),
    ({"severity": [{"type": "CVSS_V4", "score": "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H"}],
      "database_specific": {"severity": "CRITICAL"}}, "P0"),
    ({"database_specific": {"severity": "MODERATE"}}, "P2"),
    ({}, "P1"),
])
def test_osv_severity(vuln, sev):
    assert nf.osv_severity(vuln) == sev


def test_parse_osv_end_to_end():
    data = {"results": [{"source": {"path": "/r/package-lock.json"}, "packages": [
        {"package": {"name": "lodash"}, "vulnerabilities": [
            {"id": "GHSA-1", "summary": "proto pollution",
             "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}]}]}]}]}
    out = list(nf.parse_osv(data, "/r"))
    assert len(out) == 1
    assert out[0]["severity"] == "P0"
    assert out[0]["locations"][0]["path"] == "package-lock.json"
