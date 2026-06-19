from server.journal import Entry
from server.labor import split_entry, aggregate, monthly_trend, build_labor_report


def _raw(human, ai):
    h = "\n".join(f"- {x}" for x in human)
    a = "\n".join(f"- {x}" for x in ai)
    return (f"### 2026-06-10 — t\n\n**Session focus:** f\n\n"
            f"**Human-driven decisions:**\n{h}\n\n**AI execution:**\n{a}\n\n"
            f"**Tags:** domain: backend · activity: design\n")


def _entry(repo="r", date_="2026-06-10", title="t", human=("a",), ai=("b",)):
    return Entry(date=date_, title=title, repo=repo, category="Work",
                 domains=["backend"], activities=["design"], tools=[], raw=_raw(human, ai))


def test_split_entry_counts():
    s = split_entry(_entry(human=["picked star schema", "set a bar"], ai=["wrote the migration"]))
    assert s.human_bullets == 2 and s.ai_bullets == 1
    assert s.human_words == 6 and s.ai_words == 3


def test_aggregate_shares():
    entries = [_entry(human=["a b", "c", "d"], ai=["e", "f"])]
    agg = aggregate(entries)
    assert agg["human_bullets"] == 3 and agg["ai_bullets"] == 2
    assert agg["share_bullets"] == 60
    assert agg["share_words"] is not None


def test_aggregate_zero_guard():
    e = Entry(date="2026-06-10", title="t", repo="r", category="Work",
              domains=["backend"], activities=["design"], tools=[], raw="")
    agg = aggregate([e])
    assert agg["share_bullets"] is None and agg["share_words"] is None
    assert aggregate([])["share_bullets"] is None


def test_monthly_trend_groups_by_month():
    entries = [_entry(date_="2026-05-02"), _entry(date_="2026-05-20"), _entry(date_="2026-06-01")]
    trend = monthly_trend(entries)
    assert [(m, n) for (m, _share, n) in trend] == [("2026-05", 2), ("2026-06", 1)]


def test_build_labor_report_has_caption_overall_and_trend():
    entries = [_entry(repo="portal", date_="2026-06-10", human=["a", "b"], ai=["c"])]
    md, stats = build_labor_report("Jo", entries, scope="all", label="June 2026", detail="summary")
    assert "descriptive proxy" in md
    assert "## Overall" in md and "Direction share:" in md
    assert "## portal" in md
    assert "Monthly trend" in md and "2026-06" in md
    assert stats["share_bullets"] == 67


def test_build_labor_report_detail_entries_lists_per_entry():
    entries = [_entry(repo="portal", title="chose schema", human=["a", "b", "c"], ai=["d"])]
    md, _ = build_labor_report("Jo", entries, scope="all", label="L", detail="entries")
    assert "chose schema   3/1 bullets · 75%" in md


def test_build_labor_report_empty():
    md, stats = build_labor_report("Jo", [], scope="all", label="L", detail="summary")
    assert "_No entries in this window._" in md
    assert stats["entries"] == 0


from server.digest import build_digest


def test_digest_shows_direction_share_when_bullets():
    entries = [_entry(repo="portal", human=["a", "b"], ai=["c"])]
    md, _ = build_digest("Jo", entries, [], scope="all", label="L", detail="titles")
    assert "Direction share:" in md and "by bullets" in md


def test_digest_omits_direction_share_without_bullets():
    bare = Entry(date="2026-06-10", title="t", repo="portal", category="Work",
                 domains=["backend"], activities=["design"], tools=[], raw="")
    md, _ = build_digest("Jo", [bare], [], scope="all", label="L", detail="titles")
    assert "Direction share:" not in md


from pathlib import Path
from server.config import Config
from server.service import JournalService

_ROOT = Path(__file__).resolve().parents[1]
_SEED = _ROOT / "work-vocab.toml"
_LOG = dict(session_focus="f", source="s", domains=["backend"], activities=["design"],
            human_decisions=["picked A", "set bar"], ai_execution=["did X"])


def _svc(tmp_path):
    cfg = Config(owner_name="Jo", owner_identities=["jo@x.com", "Jo"],
                 journal_path=tmp_path / "J.md", repo_roots=[], dev_domains=["github.com"])
    return JournalService(cfg, seed_vocab=_SEED, local_vocab=tmp_path / "v.toml",
                          rules_path=_ROOT / "RULES.md")


def test_division_of_labor_reports_share(tmp_path):
    svc = _svc(tmp_path)
    svc.log_decision(repo="portal", category="work", title="t", **_LOG)
    res = svc.division_of_labor(period="month", basis="to-date")
    assert res["status"] == "ok"
    assert "Direction share:" in res["report"] and "## portal" in res["report"]
    assert res["stats"]["share_bullets"] == 67


def test_division_of_labor_scope_work(tmp_path):
    svc = _svc(tmp_path)
    svc.log_decision(repo="workrepo", category="work", title="t", **_LOG)
    svc.log_decision(repo="diary", category="personal", title="t", **_LOG)
    work = svc.division_of_labor(scope="work")["report"]
    assert "workrepo" in work and "diary" not in work


def test_division_of_labor_blocks_customer_data(tmp_path):
    svc = _svc(tmp_path)
    import server.journal as J
    import datetime
    jr = J.parse(J.new_journal_text())
    jr.repo_category["portal"] = "Work"
    jr.repo_order.setdefault("Work", []).append("portal")
    jr.entries.append(J.Entry(date=datetime.date.today().isoformat(), title="ping alice@acme.com",
                              repo="portal", category="Work", domains=["backend"],
                              activities=["design"], tools=[]))
    J.write_atomic(svc.cfg.journal_path, J.render(jr, svc._vocab()))
    # detail="entries" renders titles, where the planted email lives, so the egress scan sees it.
    res = svc.division_of_labor(scope="all", detail="entries")
    assert res["status"] == "blocked" and "alice@acme.com" in res["message"]
