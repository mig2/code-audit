import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"))
import detect_repo


def _run(monkeypatch, repo, out, *extra):
    monkeypatch.setattr(sys, "argv", ["detect_repo.py", str(repo), "--out", str(out), *extra])
    detect_repo.main()
    return json.loads((out / "repo-profile.json").read_text())


def _write(p, text="x = 1\n"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_python_service(tmp_path, monkeypatch):
    repo = tmp_path / "svc"
    _write(repo / "pyproject.toml",
           '[project]\nname = "svc"\ndependencies = ["fastapi", "uvicorn"]\n')
    _write(repo / "Dockerfile", "FROM python:3.13\n")
    _write(repo / "app" / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    _write(repo / "tests" / "test_main.py", "def test_x():\n    assert True\n")

    p = _run(monkeypatch, repo, tmp_path / "out")
    assert p["repo"] == str(repo.resolve())
    assert p["scope"] == "."
    assert p["primary_language"] == "python"
    assert p["languages"][0]["language"] == "python"
    assert p["is_service"] is True
    assert "Dockerfile" in p["service_evidence"]
    assert "dep:fastapi" in p["service_evidence"]
    assert p["is_monorepo"] is False and p["subprojects"] == []
    assert "pyproject.toml" in p["manifests"]
    assert p["loc"]["source"] > 0 and p["loc"]["test"] > 0
    # git metadata is tolerated when absent
    for k in ("commit", "branch", "remote", "host"):
        assert k in p


def test_monorepo_subprojects(tmp_path, monkeypatch):
    repo = tmp_path / "mono"
    for name in ("a", "b"):
        _write(repo / "packages" / name / "package.json", '{"name": "%s"}' % name)
        _write(repo / "packages" / name / "index.js", "module.exports = 1;\n")
    _write(repo / "node_modules" / "dep" / "package.json", '{"name": "dep"}')

    p = _run(monkeypatch, repo, tmp_path / "out")
    assert p["is_monorepo"] is True
    assert [s["name"] for s in p["subprojects"]] == ["a", "b"]
    assert p["subprojects"][0]["path"] == "packages/a"
    assert p["subprojects"][0]["manifests"] == ["package.json"]
    assert p["primary_language"] == "javascript"


def test_path_restricts_scope(tmp_path, monkeypatch):
    repo = tmp_path / "mixed"
    _write(repo / "py" / "x.py", "print(1)\n")
    _write(repo / "go" / "main.go", "package main\nfunc main() {}\n")

    full = _run(monkeypatch, repo, tmp_path / "full")
    assert {l["language"] for l in full["languages"]} == {"python", "go"}

    scoped = _run(monkeypatch, repo, tmp_path / "scoped", "--path", "py")
    assert scoped["scope"] == "py"
    assert [l["language"] for l in scoped["languages"]] == ["python"]
