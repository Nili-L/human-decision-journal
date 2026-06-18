from server.coverage import RepoCoverage, build_report


def _rc(repo, cat, active, logged, subjects=None):
    return RepoCoverage(repo=repo, category=cat, active=set(active),
                        logged=set(logged), subjects=subjects or {})


def test_repo_coverage_math():
    rc = _rc("a", "Work", {"2026-06-01", "2026-06-02", "2026-06-03"}, {"2026-06-01"})
    assert rc.active_days == 3
    assert rc.documented_days == 1
    assert rc.coverage == 33
    assert rc.gap_days == ["2026-06-02", "2026-06-03"]


def test_headline_hides_repo_names():
    repos = [_rc("secret-client", "Work", {"2026-06-01", "2026-06-02"}, {"2026-06-01"})]
    md, stats = build_report("Jo", repos, scope="work", level="headline")
    assert "secret-client" not in md
    assert "overall:" in md
    assert stats["coverage_pct"] == 50


def test_summary_shows_repo_no_dates():
    repos = [_rc("proj", "Work", {"2026-06-01", "2026-06-02"}, {"2026-06-01"})]
    md, _ = build_report("Jo", repos, scope="work", level="summary")
    assert "proj" in md and "coverage: 50%" in md
    assert "gap days:" not in md           # gap detail not shown at summary
    assert "2026-06-02" not in md.split("## proj")[1]   # no per-repo gap dates


def test_detailed_shows_gap_dates_full_shows_subjects():
    repos = [_rc("proj", "Work", {"2026-06-01", "2026-06-02"}, {"2026-06-01"},
                 subjects={"2026-06-02": ["refactor nav"]})]
    md_d, _ = build_report("Jo", repos, scope="work", level="detailed")
    assert "2026-06-02" in md_d and "refactor nav" not in md_d
    md_f, _ = build_report("Jo", repos, scope="work", level="full")
    assert "2026-06-02" in md_f and "refactor nav" in md_f


import os, subprocess
from pathlib import Path
from server.config import Config
from server.service import JournalService

_ROOT = Path(__file__).resolve().parents[1]
_SEED = _ROOT / "work-vocab.toml"
_LOG = dict(session_focus="f", source="s", domains=["backend"], activities=["design"],
            human_decisions=["d"], ai_execution=["a"])


def _init(path, email="jo@x.com"):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", email], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "A"], cwd=path, check=True, capture_output=True)


def _commit(path, date, subject, email="jo@x.com"):
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{date}T12:00:00",
           "GIT_COMMITTER_DATE": f"{date}T12:00:00"}
    (path / f"{date}-{subject}").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "-c", f"user.email={email}", "-c", "user.name=A",
                    "commit", "-qm", subject], cwd=path, check=True, capture_output=True, env=env)


def _svc(tmp_path):
    roots = tmp_path / "roots"
    cfg = Config(owner_name="Jo", owner_identities=["jo@x.com", "Jo"],
                 journal_path=tmp_path / "J.md", repo_roots=[roots],
                 dev_domains=["github.com"])
    svc = JournalService(cfg, seed_vocab=_SEED, local_vocab=tmp_path / "v.toml",
                         rules_path=_ROOT / "RULES.md")
    return svc, roots


def test_coverage_counts_and_gaps(tmp_path):
    import datetime
    svc, roots = _svc(tmp_path)
    repo = roots / "portal"; _init(repo)
    for d in ("2026-06-01", "2026-06-02", "2026-06-03"):
        _commit(repo, d, "work")
    svc.log_decision(repo="portal", category="work", title="t", **_LOG)
    today = datetime.date.today().isoformat()
    _commit(repo, today, "today-work")

    res = svc.coverage_report(level="detailed")
    assert res["status"] == "ok"
    assert "portal" in res["report"]
    assert res["stats"]["active_days"] == 4
    assert res["stats"]["documented_days"] == 1     # only 'today' has an entry
    assert "gap days:" in res["report"]


def test_scope_work_excludes_personal_and_uncategorized(tmp_path):
    svc, roots = _svc(tmp_path)
    for name, cat in (("workrepo", "work"), ("personalrepo", "personal")):
        r = roots / name; _init(r); _commit(r, "2026-06-01", "c")
        svc.log_decision(repo=name, category=cat, title="t", **_LOG)
    uncat = roots / "uncat"; _init(uncat); _commit(uncat, "2026-06-01", "c")

    work = svc.coverage_report(scope="work")["report"]
    assert "workrepo" in work
    assert "personalrepo" not in work and "uncat" not in work

    allr = svc.coverage_report(scope="all")["report"]
    assert "workrepo" in allr and "personalrepo" in allr and "uncat" in allr


def test_full_level_redacts_commit_subjects(tmp_path):
    svc, roots = _svc(tmp_path)
    repo = roots / "leaky"; _init(repo)
    _commit(repo, "2026-06-01", "ping client alice@acme.com about it")
    res = svc.coverage_report(level="full", scope="all")
    assert res["status"] == "ok"
    assert "alice@acme.com" not in res["report"]
    assert "[redacted]" in res["report"]
