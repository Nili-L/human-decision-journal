from datetime import date, timedelta
from server.digest import period_window

TODAY = date(2026, 6, 18)  # a Thursday


def _win(period, basis):
    s, u, _label = period_window(period, basis, None, None, TODAY)
    return s, u


def test_week_windows():
    assert _win("week", "rolling") == ("2026-06-12", "2026-06-18")
    assert _win("week", "calendar") == ("2026-06-12", "2026-06-18")
    assert _win("week", "to-date") == ("2026-06-14", "2026-06-18")   # Sunday start
    assert _win("week", "previous") == ("2026-06-07", "2026-06-13")  # Sun–Sat


def test_month_windows():
    assert _win("month", "rolling") == ((TODAY - timedelta(days=29)).isoformat(), "2026-06-18")
    assert _win("month", "calendar") == ("2026-05-19", "2026-06-18")
    assert _win("month", "to-date") == ("2026-06-01", "2026-06-18")
    assert _win("month", "previous") == ("2026-05-01", "2026-05-31")


def test_quarter_windows():
    assert _win("quarter", "rolling") == ((TODAY - timedelta(days=89)).isoformat(), "2026-06-18")
    assert _win("quarter", "calendar") == ("2026-03-19", "2026-06-18")
    assert _win("quarter", "to-date") == ("2026-04-01", "2026-06-18")
    assert _win("quarter", "previous") == ("2026-01-01", "2026-03-31")


def test_explicit_override_wins():
    s, u, label = period_window("month", "to-date", "2026-01-05", "2026-02-10", TODAY)
    assert (s, u) == ("2026-01-05", "2026-02-10")
    assert "2026-01-05 → 2026-02-10" in label


def test_partial_override_defaults_until_to_today():
    s, u, _ = period_window("month", "to-date", "2026-01-05", None, TODAY)
    assert s == "2026-01-05" and u == "2026-06-18"


from server.digest import build_digest
from server.journal import Entry


def _entry(repo, date_, title, domains=("backend",), acts=("design",), raw=""):
    return Entry(date=date_, title=title, repo=repo, category="Work",
                 domains=list(domains), activities=list(acts), tools=[], raw=raw)


def test_digest_summary_and_titles():
    entries = [_entry("portal", "2026-06-10", "chose schema"),
               _entry("portal", "2026-06-11", "fixed race"),
               _entry("site", "2026-06-12", "new nav")]
    firsts = [("2026-06-10", "domain", "backend", "portal")]
    md, stats = build_digest("Jo", entries, firsts, scope="all",
                             label="June 2026", detail="titles")
    assert "Decisions logged: 3 across 2 project(s)" in md
    assert "## portal" in md and "## site" in md
    assert "- 2026-06-10 — chose schema" in md
    assert "New firsts: domain: backend" in md
    assert stats["entries"] == 3 and stats["projects"] == 2


def test_digest_full_detail_includes_bullets():
    raw = ("### 2026-06-10 — chose schema\n\n**Session focus:** f\n\n"
           "**Human-driven decisions:**\n- picked star schema\n\n"
           "**AI execution:**\n- wrote migration\n\n**Tags:** domain: backend · activity: design\n")
    md, _ = build_digest("Jo", [_entry("portal", "2026-06-10", "chose schema", raw=raw)],
                         [], scope="all", label="L", detail="full")
    assert "picked star schema" in md
    assert "wrote migration" not in md   # only Human-driven decisions, not AI execution


def test_digest_empty_window():
    md, stats = build_digest("Jo", [], [], scope="all", label="L", detail="titles")
    assert "_No entries in this window._" in md
    assert stats["entries"] == 0


import datetime
from pathlib import Path
from server.config import Config
from server.service import JournalService

_ROOT = Path(__file__).resolve().parents[1]
_SEED = _ROOT / "work-vocab.toml"
_LOG = dict(session_focus="f", source="s", domains=["backend"], activities=["design"],
            human_decisions=["d"], ai_execution=["a"])


def _svc(tmp_path):
    cfg = Config(owner_name="Jo", owner_identities=["jo@x.com", "Jo"],
                 journal_path=tmp_path / "J.md", repo_roots=[], dev_domains=["github.com"])
    return JournalService(cfg, seed_vocab=_SEED, local_vocab=tmp_path / "v.toml",
                          rules_path=_ROOT / "RULES.md")


def test_period_summary_selects_today_only(tmp_path):
    svc = _svc(tmp_path)
    svc.log_decision(repo="portal", category="work", title="today work", **_LOG)
    res = svc.period_summary(period="week", basis="to-date")
    assert res["status"] == "ok"
    assert "portal" in res["digest"] and "today work" in res["digest"]
    assert res["stats"]["entries"] == 1


def test_period_summary_excludes_out_of_window(tmp_path):
    svc = _svc(tmp_path)
    svc.log_decision(repo="portal", category="work", title="today work", **_LOG)
    res = svc.period_summary(since="2020-01-01", until="2020-12-31")
    assert res["stats"]["entries"] == 0
    assert "_No entries in this window._" in res["digest"]


def test_period_summary_scope_work_excludes_personal(tmp_path):
    svc = _svc(tmp_path)
    svc.log_decision(repo="workrepo", category="work", title="w", **_LOG)
    svc.log_decision(repo="diary", category="personal", title="p", **_LOG)
    work = svc.period_summary(scope="work")["digest"]
    assert "workrepo" in work and "diary" not in work
    allr = svc.period_summary(scope="all")["digest"]
    assert "workrepo" in allr and "diary" in allr


def test_period_summary_blocks_customer_data(tmp_path):
    svc = _svc(tmp_path)
    import server.journal as J
    today = datetime.date.today().isoformat()
    # Craft an entry whose parsed title carries customer data (log_decision would block it
    # at write time; this proves the digest's own egress scan also catches it). Entry.raw is
    # left empty so render emits the title from fields, and parse reads it back into title.
    jr = J.parse(J.new_journal_text())
    jr.repo_category["portal"] = "Work"
    jr.repo_order.setdefault("Work", []).append("portal")
    jr.entries.append(J.Entry(date=today, title="ping alice@acme.com", repo="portal",
                              category="Work", domains=["backend"], activities=["design"], tools=[]))
    J.write_atomic(svc.cfg.journal_path, J.render(jr, svc._vocab()))
    res = svc.period_summary(scope="all")
    assert res["status"] == "blocked"
    assert "alice@acme.com" in res["message"]
