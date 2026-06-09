import subprocess
from pathlib import Path
from server.gitops import git_available, is_git_repo, remotes, sync

def _git(path, *a): subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)

def test_git_available():
    assert git_available() in (True, False)

def test_is_git_repo(tmp_path):
    assert is_git_repo(tmp_path) is False
    _git(tmp_path, "init", "-q")
    assert is_git_repo(tmp_path) is True

def test_remotes(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", "git@github.com:Jo/x.git")
    assert remotes(tmp_path)["origin"].endswith("x.git")

def test_sync_commits_when_origin_missing_reports(tmp_path):
    bare = tmp_path / "remote.git"; bare.mkdir(); _git(bare, "init", "--bare", "-q")
    work = tmp_path / "work"; work.mkdir()
    _git(work, "init", "-q"); _git(work, "config", "user.email", "jo@x.com")
    _git(work, "config", "user.name", "Jo"); _git(work, "remote", "add", "origin", str(bare))
    _git(work, "commit", "-qm", "init", "--allow-empty")
    _git(work, "push", "-q", "-u", "origin", "HEAD")
    journal = work / "DECISIONS_JOURNAL.md"; journal.write_text("# Decisions Journal\n")
    out = sync(journal, "journal: test")
    assert "1" in out or "push" in out.lower()
