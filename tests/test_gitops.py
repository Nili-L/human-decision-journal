import subprocess
from pathlib import Path
from server.gitops import git_available, is_git_repo, remotes, sync, author_email_domains

def _git(path, *a): subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)

def test_author_email_domains(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "jo@Acme.com")
    _git(repo, "config", "user.name", "T")
    (repo / "f").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    assert author_email_domains(repo) == {"acme.com": 1}

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


from server.gitops import list_git_repos, owner_commit_dates

def _commit(path, date, email, subject):
    import os
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{date}T12:00:00",
           "GIT_COMMITTER_DATE": f"{date}T12:00:00"}
    (path / f"{date}-{subject}").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "-c", f"user.email={email}", "-c", "user.name=A",
                    "commit", "-qm", subject], cwd=path, check=True, capture_output=True, env=env)

def _init(path, email="jo@x.com"):
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", email)
    _git(path, "config", "user.name", "A")

def test_list_git_repos(tmp_path):
    root = tmp_path / "root"
    _init(root / "a"); _init(root / "b")
    (root / "notrepo").mkdir()
    found = dict(list_git_repos([root]))
    assert set(found) == {"a", "b"}

def test_owner_commit_dates_filters_owner_and_window(tmp_path):
    repo = tmp_path / "r"; _init(repo)
    _commit(repo, "2026-06-01", "jo@x.com", "mine1")
    _commit(repo, "2026-06-03", "stranger@y.com", "theirs")
    _commit(repo, "2026-06-05", "jo@x.com", "mine2")
    dates = owner_commit_dates(repo, ["jo@x.com", "Jo"])
    assert dates == {"2026-06-01", "2026-06-05"}     # stranger excluded
    windowed = owner_commit_dates(repo, ["jo@x.com"], since="2026-06-02", until="2026-06-30")
    assert windowed == {"2026-06-05"}

def test_owner_commit_dates_with_subjects(tmp_path):
    repo = tmp_path / "r2"; _init(repo)
    _commit(repo, "2026-06-01", "jo@x.com", "fixbug")
    subs = owner_commit_dates(repo, ["jo@x.com"], with_subjects=True)
    assert subs == {"2026-06-01": ["fixbug"]}
