import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "calibration" / "scripts"))
import calibration_signals as cs


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True, text=True)


def build_repo(root):
    pkg = root / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "base.py").write_text(
        "from abc import ABC, abstractmethod\n\n"
        "class Store(ABC):\n    @abstractmethod\n    def get(self, k):\n        ...\n")
    (pkg / "x.py").write_text(
        "import os\nfrom .base import Store\n\n"
        "class MemStore(Store):\n    \"\"\"In-memory store.\"\"\"\n"
        "    def get(self, k):\n        try:\n            return os.environ[k]\n"
        "        except:\n            return None\n\n"
        "def price(x):\n    \"\"\"Double.\"\"\"\n    return x * 2\n")
    (pkg / "SessionManager.py").write_text("def run():\n    print('hi')\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text(
        "from unittest import mock\nfrom app.x import MemStore\n\n"
        "def test_get():\n    with mock.patch('os.environ', {'a': '1'}):\n"
        "        assert MemStore().get('a') == '1'\n    assert MemStore().get('zz') is None\n")
    (root / "requirements.txt").write_text("requests==2.31.0\nhttpx\n")
    (root / "README.md").write_text("# App\n\nUsed by customers in production.\n\n## Install\n\n## Usage\n\n## Design\n")
    (root / "Dockerfile").write_text("FROM python:3.12\n")
    (root / "config.yaml").write_text("db: x\nport: 1\n")
    (root / "CLAUDE.md").write_text("# rules\n")


def build_audit(root, with_metrics=True):
    audit = root / ".audit" / "202609101200"
    audit.mkdir(parents=True)
    (audit / "repo-profile.json").write_text(json.dumps({
        "repo": str(root), "scope": ".", "is_service": True, "primary_language": "python",
        "languages": [{"language": "python", "loc": 30}]}))
    if with_metrics:
        (audit / "metrics.json").write_text(json.dumps({
            "source_loc": 30, "test_loc": 8, "test_to_source_ratio": 0.27, "todo_fixme_count": 0,
            "functions": {"count": 4, "p50": 3, "p90": 6, "max": 6, "over_80": []},
            "census": {"python": {}}, "hotspots": [{"path": "app/x.py"}],
            "complexity_source": {"python": "keyword-proxy"}, "import_cycles": {"python": []}}))
        (audit / "findings.json").write_text(json.dumps({"findings": [
            {"severity": "P1", "status": "new", "dimension": "security"},
            {"severity": "P3", "status": "new", "dimension": "readability"}]}))
    return audit


def run(root, audit, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["calibration_signals.py", str(root), "--audit", str(audit)])
    cs.main()
    return json.loads((audit / "calibration-signals.json").read_text())


def test_signals_on_synthetic_repo(tmp_path, monkeypatch):
    build_repo(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "feat: initial")
    (tmp_path / "app" / "y.py").write_text("def y():\n    return 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "add y\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    audit = build_audit(tmp_path)

    s = run(tmp_path, audit, monkeypatch)

    assert s["size"]["source_loc"] == 30 and s["size"]["is_service"] is True
    ind = s["indirection"]
    assert ind["interfaces"] == 1 and ind["implementations"] == 1
    assert ind["single_impl_interfaces"][0]["name"] == "Store"
    assert "app/SessionManager.py" in ind["pattern_named_files"]["top"]
    assert s["config_surface"]["env_reads"] >= 1
    assert any(c["file"] == "config.yaml" and c["keys"] == 2 for c in s["config_surface"]["config_files"])
    err = s["error_handling"]
    assert err["broad_catches"] >= 1 and err["try_blocks"] == 1 and err["print_debugging"] == 1
    assert err["error_boundary"] is False
    t = s["testing"]
    assert t["test_files"] == 1 and t["mirror_ratio"] == 1.0
    assert t["assertions"] == 2 and t["mock_calls"] == 1 and t["no_assert_tests"] == 0
    assert t["test_to_source_ratio"] == 0.27
    d = s["dependencies"]
    assert d["direct_total"] == 2 and ["requests", "httpx"] in d["duplicate_purpose"]
    assert d["pinned_ratio"] == 0.5 and d["heavy_for_purpose"] == []
    doc = s["documentation"]
    assert doc["readme_sections"] == 3 and doc["docstring_coverage"]["python"] == 0.2
    h = s["history"]
    assert h["commits"] == 2 and h["authors"] == 1 and h["ai_coauthor_commits"] == 1
    assert h["conventional_prefix_ratio"] == 0.5
    assert s["ai_assist_markers"]["instruction_files"] == ["CLAUDE.md"]
    dd = s["demand_drivers"]
    assert dd["deployment"] >= 1 and dd["users_hint"] >= 2
    assert dd["open_p0_p1"] == {"security": 1}
    assert s["passthrough"]["functions"]["count"] == 4 and s["passthrough"]["hotspots"] == ["app/x.py"]


def test_signals_without_git_or_metrics(tmp_path, monkeypatch):
    build_repo(tmp_path)
    audit = build_audit(tmp_path, with_metrics=False)
    s = run(tmp_path, audit, monkeypatch)
    assert s["history"] is None
    assert s["passthrough"] is None
    assert s["size"]["source_loc"] > 0
    assert s["testing"]["test_to_source_ratio"] is None
    assert s["ai_assist_markers"]["ai_coauthor_commits"] is None


def _ts_repo(root, boundary_line):
    src = root / "src"
    src.mkdir(parents=True)
    (src / "types.ts").write_text("export interface Msg { id: string; text: string }\n")
    (src / "port.ts").write_text(
        "import { Msg } from './types';\nexport interface Port { send(msg: Msg): Promise<void>; }\n")
    (src / "adapter.ts").write_text(
        "import { Port } from './port';\n"
        "// a rejection here only ever reaches process.on('unhandledRejection') — see #224\n"
        f"{boundary_line}\n"
        "export class Tg implements Port { async send(): Promise<void> {} }\n")
    audit = root / ".audit" / "x"
    audit.mkdir(parents=True)
    (audit / "repo-profile.json").write_text(json.dumps({
        "repo": str(root), "scope": ".", "is_service": True, "primary_language": "typescript",
        "languages": [{"language": "typescript", "loc": 10}]}))
    return audit


def test_ts_data_shapes_and_commented_boundary_are_not_counted(tmp_path, monkeypatch):
    audit = _ts_repo(tmp_path, "")
    s = run(tmp_path, audit, monkeypatch)
    ind = s["indirection"]
    assert ind["interfaces"] == 1 and ind["type_shapes"] == 1
    assert [x["name"] for x in ind["single_impl_interfaces"]] == ["Port"]
    assert ind["single_impl_interfaces"][0]["implementations"] == 1
    assert s["error_handling"]["error_boundary"] is False


def test_ts_real_boundary_is_counted(tmp_path, monkeypatch):
    audit = _ts_repo(tmp_path, "process.on('uncaughtException', (e) => { console.error(e); });")
    s = run(tmp_path, audit, monkeypatch)
    assert s["error_handling"]["error_boundary"] is True
    assert s["error_handling"]["error_boundary_evidence"] == ["src/adapter.ts:3"]


def test_no_manifests_yields_null_dependencies(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n")
    audit = tmp_path / ".audit" / "x"
    audit.mkdir(parents=True)
    s = run(tmp_path, audit, monkeypatch)
    assert s["dependencies"] is None
    assert s["size"]["file_count"] == 1
