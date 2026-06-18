import subprocess
from pathlib import Path
from server.ownership import resolve_repo_path, is_collaboration, remote_owner


def test_remote_owner_extracts_org(tmp_path):
    repo = tmp_path / "r"
    _make_repo(repo, "jo@x.com", "git@github.com:AcmeCorp/r.git")
    assert remote_owner(repo) == "acmecorp"


def test_remote_owner_none_without_remote(tmp_path):
    repo = tmp_path / "noremote"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert remote_owner(repo) is None

def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

def _make_repo(path, author_email, remote_url):
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", author_email)
    _git(path, "config", "user.name", "Tester")
    _git(path, "remote", "add", "origin", remote_url)
    (path / "f.txt").write_text("x")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "c1")

def test_resolve_repo_path(tmp_path):
    (tmp_path / "roots" / "acme").mkdir(parents=True)
    assert resolve_repo_path("acme", [tmp_path / "roots"]) == tmp_path / "roots" / "acme"
    assert resolve_repo_path("missing", [tmp_path / "roots"]) is None

def test_own_repo_is_not_collaboration(tmp_path):
    repo = tmp_path / "mine"
    _make_repo(repo, "jo@x.com", "git@github.com:Jo/mine.git")
    assert is_collaboration(repo, ["jo@x.com", "Jo"]) is False

def test_fork_of_others_is_collaboration(tmp_path):
    repo = tmp_path / "theirs"
    _make_repo(repo, "other@y.com", "git@github.com:SomeoneElse/theirs.git")
    assert is_collaboration(repo, ["jo@x.com", "Jo"]) is True

def test_substring_identity_does_not_suppress_collaboration(tmp_path):
    repo = tmp_path / "theirs2"
    _make_repo(repo, "x@y.com", "git@github.com:someoneelse/theirs2.git")
    # owner identity "me" is a substring of "someoneelse" — must NOT be treated as owner
    assert is_collaboration(repo, ["me@y.com", "me"]) is True

def test_owner_username_match_is_not_collaboration(tmp_path):
    repo = tmp_path / "mine2"
    _make_repo(repo, "me@y.com", "git@github.com:me/mine2.git")
    assert is_collaboration(repo, ["me@y.com", "me"]) is False
