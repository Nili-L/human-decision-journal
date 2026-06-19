from pathlib import Path
from server.config import Config
from server.service import JournalService

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "work-vocab.toml"

BASE = dict(session_focus="f", source="s", domains=["backend"], activities=["design"])


def make_service(tmp_path):
    cfg = Config(owner_name="Jo", owner_identities=["jo@x.com", "Jo"],
                 journal_path=tmp_path / "DECISIONS_JOURNAL.md",
                 repo_roots=[], dev_domains=["github.com"])
    return JournalService(cfg, seed_vocab=SEED, local_vocab=tmp_path / "vocab.local.toml",
                          rules_path=ROOT / "RULES.md")


def _seed(svc):
    svc.log_decision(repo="acme", category="work", title="Chose schema",
                     human_decisions=["Picked a star schema over snowflake."],
                     ai_execution=["Wrote the migration."], tools=["fastmcp"], **BASE)
    svc.log_decision(repo="diary", category="personal", title="Personal note",
                     human_decisions=["Private reflection."],
                     ai_execution=["Saved it."], **BASE)


def test_report_is_work_only(tmp_path):
    svc = make_service(tmp_path)
    _seed(svc)
    res = svc.export_authorship_report()
    assert res["status"] == "ok"
    r = res["report"]
    assert "# Authorship Report — Jo" in r
    assert "## acme" in r and "Chose schema" in r
    # Personal entry must never appear in the shareable report.
    assert "diary" not in r and "Private reflection" not in r
    assert res["stats"]["entries"] == 1 and res["stats"]["projects"] == 1


def test_report_splits_human_and_agent(tmp_path):
    svc = make_service(tmp_path)
    _seed(svc)
    r = svc.export_authorship_report()["report"]
    assert "**My decisions:**" in r
    assert "Picked a star schema over snowflake." in r
    assert "**Agent execution:**" in r
    assert "Wrote the migration." in r


def test_report_date_filter(tmp_path):
    svc = make_service(tmp_path)
    _seed(svc)
    # A window before any entry yields an empty (but well-formed) report.
    res = svc.export_authorship_report(since="2000-01-01", until="2000-12-31")
    assert res["status"] == "ok"
    assert res["stats"]["entries"] == 0
    assert "_No entries match this scope._" in res["report"]


def test_report_repo_filter(tmp_path):
    svc = make_service(tmp_path)
    _seed(svc)
    svc.log_decision(repo="other", category="work", title="Second project",
                     human_decisions=["Did a thing."], ai_execution=["Helped."], **BASE)
    r = svc.export_authorship_report(repos=["acme"])["report"]
    assert "## acme" in r and "## other" not in r


def test_report_empty_journal(tmp_path):
    svc = make_service(tmp_path)
    res = svc.export_authorship_report()
    assert res["status"] == "ok"
    assert res["stats"]["entries"] == 0


from server.report import human_decision_bullets

def test_human_decision_bullets_extracts():
    raw = ("### 2026-06-01 — t\n\n**Session focus:** f\n\n"
           "**Human-driven decisions:**\n- chose A\n- set bar B\n\n"
           "**AI execution:**\n- did X\n\n**Tags:** domain: backend · activity: design\n")
    assert human_decision_bullets(raw) == ["- chose A", "- set bar B"]


from server.report import ai_execution_bullets

def test_ai_execution_bullets_extracts():
    raw = ("### 2026-06-01 — t\n\n**Session focus:** f\n\n"
           "**Human-driven decisions:**\n- chose A\n\n"
           "**AI execution:**\n- wrote code\n- ran tests\n\n"
           "**Tags:** domain: backend · activity: design\n")
    assert ai_execution_bullets(raw) == ["- wrote code", "- ran tests"]
