from server.categorize import Signals, Guess, guess


def _sig(org=None, emails=(), path=None, collab=False):
    return Signals(remote_org=org, email_domains=tuple(emails),
                   path_prefix=path, is_collaboration=collab)


def test_high_confidence_two_axes_agree():
    target = _sig(org="acme", emails=("acme.com",), path="/r")
    labeled = [
        (_sig(org="acme", emails=("acme.com",), path="/r"), "Work"),
        (_sig(org="acme", emails=("acme.com",), path="/r"), "Work"),
    ]
    g = guess(target, labeled)
    assert g.guess == "Work"
    assert g.confidence == "high"
    assert g.reasons


def test_medium_confidence_single_axis():
    target = _sig(org="acme")
    labeled = [
        (_sig(org="acme"), "Work"),
        (_sig(org="other"), "Personal"),
    ]
    g = guess(target, labeled)
    assert g.guess == "Work"
    assert g.confidence == "medium"


def test_conflicting_signals_yield_no_guess():
    target = _sig(org="acme", path="/shared")
    labeled = [
        (_sig(org="acme", path="/shared"), "Work"),
        (_sig(org="acme", path="/shared"), "Personal"),
    ]
    g = guess(target, labeled)
    # org and path both match repos of BOTH categories -> neither axis discriminates
    assert g.guess is None
    assert g.confidence == "low"


def test_cold_start_under_two_labels():
    g = guess(_sig(org="acme"), [(_sig(org="acme"), "Work")])
    assert g.guess is None
    assert g.confidence == "low"


import subprocess
from server.categorize import signals_for


def _make_repo(path, email, remote_url):
    path.mkdir(parents=True)
    for args in (["init", "-q"], ["config", "user.email", email],
                 ["config", "user.name", "T"], ["remote", "add", "origin", remote_url]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    (path / "f").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=path, check=True, capture_output=True)


def test_signals_for_reads_repo(tmp_path):
    repo = tmp_path / "roots" / "proj"
    _make_repo(repo, "jo@acme.com", "git@github.com:acme/proj.git")
    s = signals_for(repo, ["jo@x.com", "Jo"])
    assert s.remote_org == "acme"
    assert s.email_domains == ("acme.com",)
    assert s.path_prefix == str(repo.parent)
    assert s.is_collaboration is True   # org 'acme' is not in owner identities


from pathlib import Path as _P
from server.config import Config
from server.service import JournalService
from server.addons import categorization

_ROOT = _P(__file__).resolve().parents[1]
_SEED = _ROOT / "work-vocab.toml"
_LOG = dict(session_focus="f", source="s", domains=["backend"], activities=["design"],
            human_decisions=["d"], ai_execution=["a"])


def _svc(tmp_path, state_dir):
    roots = tmp_path / "roots"
    cfg = Config(owner_name="Jo", owner_identities=["jo@x.com", "Jo"],
                 journal_path=tmp_path / "J.md", repo_roots=[roots],
                 dev_domains=["github.com"], categorization_enabled=True,
                 state_dir=state_dir)
    return JournalService(cfg, seed_vocab=_SEED, local_vocab=tmp_path / "v.toml",
                          rules_path=_ROOT / "RULES.md"), roots


def test_categorize_repo_guesses_work(tmp_path):
    state = tmp_path / "state"
    svc, roots = _svc(tmp_path, state)
    for name in ("w1", "w2"):
        _make_repo(roots / name, "jo@acme.com", f"git@github.com:acme/{name}.git")
        svc.log_decision(repo=name, category="work", title="t", **_LOG)
    _make_repo(roots / "target", "jo@acme.com", "git@github.com:acme/target.git")

    before = (tmp_path / "J.md").read_text()
    res = categorization.categorize_repo(svc, "target")
    after = (tmp_path / "J.md").read_text()

    assert res["status"] == "ok"
    assert res["guess"] == "Work"
    assert res["reasons"]
    # read-only: the guess must not touch the journal, and reasons must not leak into it
    assert before == after
    for reason in res["reasons"]:
        assert reason not in after
    # PII-bearing cache written OUTSIDE any repo, under state_dir
    assert (state / "categories.local.json").exists()


def test_categorize_repo_unknown_path(tmp_path):
    svc, _ = _svc(tmp_path, tmp_path / "state")
    res = categorization.categorize_repo(svc, "does-not-exist")
    assert res["status"] == "no_path"
    assert res["guess"] is None


def test_rules_snippet_mentions_tool():
    assert "guess_category" in categorization.rules_snippet()
