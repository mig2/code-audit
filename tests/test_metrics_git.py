import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "audit" / "scripts"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)


def test_git_authors_does_not_block_on_piped_stdin(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.py").write_text("x = 1\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "one")

    code = (f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import metrics; "
            f"print(metrics.git_authors({str(repo)!r}, 'a.py'))")
    # stdin is an open pipe that never closes: git shortlog would read it forever
    proc = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise AssertionError("git_authors blocked on stdin")
    finally:
        proc.stdin.close()
    assert proc.stdout.read().strip() == "1"
