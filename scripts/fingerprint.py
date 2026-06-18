#!/usr/bin/env python3
"""code-audit shared library: findings schema, fingerprinting, I/O.

Also a CLI:  fingerprint.py add-finding FINDINGS.json --json '{...}'
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

DIMENSIONS = [
    "design", "structure", "data-flow", "security", "testing", "maintainability",
    "readability", "correctness", "performance", "dependencies", "operability",
]
SEVERITIES = ["P0", "P1", "P2", "P3", "INFO"]
SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
CONFIDENCES = ["high", "medium", "low"]
EFFORTS = ["XS", "S", "M", "L", "XL"]
STATUSES = ["new", "persisting", "fixed", "suppressed"]

SCHEMA_VERSION = "1.0"


def normalize_snippet(text: str) -> str:
    """Collapse whitespace; keep identifiers. Used in fingerprints."""
    return re.sub(r"\s+", " ", (text or "").strip())


def compute_fingerprint(rule: str, rel_path: str, snippet_or_key: str) -> str:
    h = hashlib.sha256()
    h.update(rule.encode())
    h.update(b"\x00")
    h.update(rel_path.replace("\\", "/").encode())
    h.update(b"\x00")
    h.update(normalize_snippet(snippet_or_key).encode())
    return "sha256:" + h.hexdigest()


def new_finding(*, dimension, rule, source, severity, title, description,
                recommendation="", locations=None, language=None,
                confidence="high", effort="M", snippet_key=None,
                related_fingerprints=None) -> dict:
    locations = locations or []
    if dimension not in DIMENSIONS:
        raise ValueError(f"bad dimension {dimension!r}; one of {DIMENSIONS}")
    if severity not in SEVERITIES:
        raise ValueError(f"bad severity {severity!r}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"bad confidence {confidence!r}")
    if effort not in EFFORTS:
        raise ValueError(f"bad effort {effort!r}")
    path = locations[0]["path"] if locations else ""
    key = snippet_key or (locations[0].get("snippet", "") if locations else title)
    return {
        "id": None,  # assigned on save
        "fingerprint": compute_fingerprint(rule, path, key),
        "dimension": dimension,
        "rule": rule,
        "source": source,
        "severity": severity,
        "confidence": confidence,
        "effort": effort,
        "title": title.strip()[:200],
        "description": description.strip(),
        "recommendation": recommendation.strip(),
        "locations": [
            {
                "path": l["path"].replace("\\", "/"),
                "startLine": l.get("startLine"),
                "endLine": l.get("endLine", l.get("startLine")),
                "snippetHash": ("sha256:" + hashlib.sha256(
                    normalize_snippet(l.get("snippet", "")).encode()).hexdigest())
                if l.get("snippet") else None,
                "snippet": (l.get("snippet") or "")[:500] or None,
            }
            for l in locations
        ],
        "language": language,
        "status": "new",
        "suppressReason": None,
        "relatedFingerprints": related_fingerprints or [],
        "tracker": {"url": None, "id": None},
    }


def load_findings(path: Path) -> dict:
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    return {"schema": SCHEMA_VERSION, "audit": {}, "findings": []}


def save_findings(doc: dict, path: Path) -> None:
    # assign ids, dedupe by fingerprint (first wins; merge locations)
    seen = {}
    ordered = []
    for f in doc["findings"]:
        fp = f["fingerprint"]
        if fp in seen:
            known = {(l["path"], l.get("startLine")) for l in seen[fp]["locations"]}
            for l in f["locations"]:
                if (l["path"], l.get("startLine")) not in known:
                    seen[fp]["locations"].append(l)
        else:
            seen[fp] = f
            ordered.append(f)
    year = date.today().year
    for i, f in enumerate(ordered, 1):
        f["id"] = f.get("id") or f"CA-{year}-{i:04d}"
    # renumber gaps deterministically by sort order
    ordered.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9),
                                f["dimension"], f["rule"], f["fingerprint"]))
    for i, f in enumerate(ordered, 1):
        f["id"] = f"CA-{year}-{i:04d}"
    doc["findings"] = ordered
    Path(path).write_text(json.dumps(doc, indent=2) + "\n")


def severity_counts(findings, statuses=("new", "persisting")):
    out = {s: 0 for s in SEVERITIES}
    for f in findings:
        if f["status"] in statuses:
            out[f["severity"]] += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-finding", help="append a claude-review finding")
    add.add_argument("findings_file")
    add.add_argument("--json", required=True,
                     help="JSON object: dimension, rule, severity, title, description,"
                          " recommendation, confidence, effort, language, snippet_key,"
                          " locations:[{path,startLine,endLine,snippet}]")
    args = ap.parse_args()
    if args.cmd == "add-finding":
        spec = json.loads(args.json)
        spec.setdefault("source", "claude-review")
        f = new_finding(**spec)
        doc = load_findings(Path(args.findings_file))
        before = len(doc["findings"])
        doc["findings"].append(f)
        save_findings(doc, Path(args.findings_file))
        after = len(json.loads(Path(args.findings_file).read_text())["findings"])
        status = "added" if after > before else "merged into existing fingerprint"
        print(f"{status}: {f['fingerprint']}  [{f['severity']}] {f['title']}")


if __name__ == "__main__":
    main()
