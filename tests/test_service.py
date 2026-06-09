import pytest
from pathlib import Path
from server.config import Config
from server.service import JournalService

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "work-vocab.toml"

def make_service(tmp_path, repo_roots=None):
    cfg = Config(owner_name="Jo", owner_identities=["jo@x.com", "Jo"],
                 journal_path=tmp_path / "DECISIONS_JOURNAL.md",
                 repo_roots=repo_roots or [], dev_domains=["github.com"])
    return JournalService(cfg, seed_vocab=SEED, local_vocab=tmp_path / "vocab.local.toml",
                          rules_path=ROOT / "RULES.md")

BASE = dict(title="t", session_focus="f", human_decisions=["d"], ai_execution=["a"],
            source="s", domains=["backend"], activities=["design"], tools=["fastmcp"])

def test_new_repo_requires_category(tmp_path):
    svc = make_service(tmp_path)
    res = svc.log_decision(repo="acme", **BASE)
    assert res["status"] == "needs_category"

def test_log_writes_and_confirms(tmp_path):
    svc = make_service(tmp_path)
    res = svc.log_decision(repo="acme", category="work", **BASE)
    assert res["status"] == "logged"
    assert "journal updated: acme — t" in res["message"]
    text = (tmp_path / "DECISIONS_JOURNAL.md").read_text()
    assert "## acme" in text and "domain: backend" in text
    assert "+ first" in res["message"]

def test_privacy_hard_block(tmp_path):
    svc = make_service(tmp_path)
    bad = dict(BASE); bad["human_decisions"] = ["email alice@acme.com"]
    res = svc.log_decision(repo="acme", category="work", **bad)
    assert res["status"] == "blocked"
    assert "email" in res["message"]
    assert not (tmp_path / "DECISIONS_JOURNAL.md").exists() or "alice@acme.com" not in (tmp_path / "DECISIONS_JOURNAL.md").read_text()

def test_off_vocabulary_rejected(tmp_path):
    svc = make_service(tmp_path)
    bad = dict(BASE); bad["domains"] = ["nope"]
    res = svc.log_decision(repo="acme", category="work", **bad)
    assert res["status"] == "bad_tags"
    assert "domain:nope" in res["message"]

def test_existing_repo_no_recategory(tmp_path):
    svc = make_service(tmp_path)
    svc.log_decision(repo="acme", category="work", **BASE)
    res = svc.log_decision(repo="acme", **BASE)
    assert res["status"] == "logged"

def test_sync_status_local_only_without_git(tmp_path):
    # journal_path in a non-git temp dir → sync cannot push
    svc = make_service(tmp_path)
    svc.log_decision(repo="acme", category="work", **BASE)
    res = svc.sync_journal()
    assert res["status"] in ("local_only", "error")
    assert "entries" in res["message"]

def test_collaboration_autotag(tmp_path):
    import subprocess
    roots = tmp_path / "roots"; repo = roots / "theirs"; repo.mkdir(parents=True)
    def g(*a): subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    g("init", "-q"); g("config", "user.email", "other@y.com"); g("config", "user.name", "Other")
    g("remote", "add", "origin", "git@github.com:SomeoneElse/theirs.git")
    (repo / "f").write_text("x"); g("add", "-A"); g("commit", "-qm", "c")
    svc = make_service(tmp_path, repo_roots=[roots])
    svc.log_decision(repo="theirs", category="work", **BASE)
    text = (tmp_path / "DECISIONS_JOURNAL.md").read_text()
    assert "collaboration" in text
