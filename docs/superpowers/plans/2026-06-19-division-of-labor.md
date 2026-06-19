# Division-of-Labor Metric Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only "direction share" metric — the owner's decision bullets ÷ all bullets (by bullets and words) — surfaced as a line in the period digest and as a standalone `division_of_labor` tool with per-project breakdown and monthly trend.

**Architecture:** Pure metric in `server/labor.py` (split each entry into human/agent counts, aggregate, trend, render). `digest.build_digest` gains one omittable share line. `JournalService.division_of_labor` windows + scopes entries (reusing `digest.period_window`), renders, egress-scans. Registered as a core read tool.

**Tech Stack:** Python 3.11+, FastMCP, stdlib (`collections`, `datetime`), pytest. Reuses `report.py` (bullet extractors) and `digest.period_window`.

**Spec:** `docs/DIVISION-OF-LABOR.md`. **Branch:** `feature/division-of-labor` (checked out, off `main`).

Run the suite at each gate: `cd /tmp/hdj && . .venv/bin/activate && python3 -m pytest -q`.

---

## File Structure

- **Modify** `server/report.py` — add `ai_execution_bullets(raw)`.
- **Create** `server/labor.py` — `split_entry`, `aggregate`, `monthly_trend`, `build_labor_report`, `CAPTION`.
- **Modify** `server/digest.py` — add the omittable Direction-share line to `build_digest`.
- **Modify** `server/service.py` — `division_of_labor(...)`.
- **Modify** `server/main.py` — register the `division_of_labor` tool.
- **Create** `tests/test_labor.py` — split/aggregate/trend/render/service/egress.

---

## Task 1: `ai_execution_bullets` in report.py

**Files:**
- Modify: `server/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
from server.report import ai_execution_bullets

def test_ai_execution_bullets_extracts():
    raw = ("### 2026-06-01 — t\n\n**Session focus:** f\n\n"
           "**Human-driven decisions:**\n- chose A\n\n"
           "**AI execution:**\n- wrote code\n- ran tests\n\n"
           "**Tags:** domain: backend · activity: design\n")
    assert ai_execution_bullets(raw) == ["- wrote code", "- ran tests"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_report.py::test_ai_execution_bullets_extracts -v`
Expected: FAIL with `ImportError: cannot import name 'ai_execution_bullets'`.

- [ ] **Step 3: Implement**

In `server/report.py`, add directly after `human_decision_bullets`:

```python
def ai_execution_bullets(raw: str) -> list[str]:
    """The agent's AI-execution bullets (each '- '-prefixed) from a rendered entry."""
    return _bullets(_sections(raw).get("**AI execution:**", []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_report.py::test_ai_execution_bullets_extracts -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/report.py tests/test_report.py
git commit -m "feat(report): ai_execution_bullets() helper"
```

---

## Task 2: `labor.py` — `split_entry` + `aggregate`

**Files:**
- Create: `server/labor.py`
- Test: `tests/test_labor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_labor.py`:

```python
from server.journal import Entry
from server.labor import split_entry, aggregate


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
    assert s.human_words == 6 and s.ai_words == 3   # "picked star schema"+"set a bar"=6; "wrote the migration"=3


def test_aggregate_shares():
    entries = [_entry(human=["a b", "c", "d"], ai=["e", "f"])]  # 3 human / 2 ai bullets
    agg = aggregate(entries)
    assert agg["human_bullets"] == 3 and agg["ai_bullets"] == 2
    assert agg["share_bullets"] == 60        # 3 / 5
    assert agg["share_words"] is not None


def test_aggregate_zero_guard():
    e = Entry(date="2026-06-10", title="t", repo="r", category="Work",
              domains=["backend"], activities=["design"], tools=[], raw="")  # no bullets
    agg = aggregate([e])
    assert agg["share_bullets"] is None and agg["share_words"] is None
    assert aggregate([])["share_bullets"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_labor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.labor'`.

- [ ] **Step 3: Implement**

Create `server/labor.py`:

```python
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

from server.report import human_decision_bullets, ai_execution_bullets

CAPTION = ("> Direction share is a *descriptive proxy* for how much of the logged work was "
           "the owner directing vs. the agent executing — not a measure of effort, value, "
           'or "who did more."')


@dataclass
class Split:
    human_bullets: int
    ai_bullets: int
    human_words: int
    ai_words: int


def _text(b: str) -> str:
    return b[2:] if b.startswith("- ") else b


def _words(bullets) -> int:
    return sum(len(_text(b).split()) for b in bullets)


def split_entry(entry) -> Split:
    h = human_decision_bullets(entry.raw)
    a = ai_execution_bullets(entry.raw)
    return Split(len(h), len(a), _words(h), _words(a))


def _share(human: int, total: int):
    return round(100 * human / total) if total else None


def aggregate(entries) -> dict:
    hb = ab = hw = aw = 0
    for e in entries:
        s = split_entry(e)
        hb += s.human_bullets
        ab += s.ai_bullets
        hw += s.human_words
        aw += s.ai_words
    return {"human_bullets": hb, "ai_bullets": ab, "human_words": hw, "ai_words": aw,
            "share_bullets": _share(hb, hb + ab), "share_words": _share(hw, hw + aw)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_labor.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add server/labor.py tests/test_labor.py
git commit -m "feat(labor): split_entry + aggregate (zero-guarded shares)"
```

---

## Task 3: `labor.py` — `monthly_trend` + `build_labor_report`

**Files:**
- Modify: `server/labor.py`
- Test: `tests/test_labor.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_labor.py`:

```python
from server.labor import monthly_trend, build_labor_report


def test_monthly_trend_groups_by_month():
    entries = [_entry(date_="2026-05-02"), _entry(date_="2026-05-20"), _entry(date_="2026-06-01")]
    trend = monthly_trend(entries)
    assert [(m, n) for (m, _share, n) in trend] == [("2026-05", 2), ("2026-06", 1)]


def test_build_labor_report_has_caption_overall_and_trend():
    entries = [_entry(repo="portal", date_="2026-06-10", human=["a", "b"], ai=["c"])]
    md, stats = build_labor_report("Jo", entries, scope="all", label="June 2026", detail="summary")
    assert "descriptive proxy" in md                      # caption present
    assert "## Overall" in md and "Direction share:" in md
    assert "## portal" in md
    assert "Monthly trend" in md and "2026-06" in md
    assert stats["share_bullets"] == 67                   # 2 / 3


def test_build_labor_report_detail_entries_lists_per_entry():
    entries = [_entry(repo="portal", title="chose schema", human=["a", "b", "c"], ai=["d"])]
    md, _ = build_labor_report("Jo", entries, scope="all", label="L", detail="entries")
    assert "chose schema   3/1 bullets · 75%" in md


def test_build_labor_report_empty():
    md, stats = build_labor_report("Jo", [], scope="all", label="L", detail="summary")
    assert "_No entries in this window._" in md
    assert stats["entries"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_labor.py -k "trend or build_labor" -v`
Expected: FAIL with `ImportError: cannot import name 'monthly_trend'`.

- [ ] **Step 3: Implement**

In `server/labor.py`, add at the end:

```python
def monthly_trend(entries):
    by_month = defaultdict(list)
    for e in entries:
        by_month[e.date[:7]].append(e)
    out = []
    for month in sorted(by_month):
        out.append((month, aggregate(by_month[month])["share_bullets"], len(by_month[month])))
    return out


def _share_line(agg) -> str:
    sb, sw = agg["share_bullets"], agg["share_words"]
    total_b = agg["human_bullets"] + agg["ai_bullets"]
    b = f"{sb}% by bullets ({agg['human_bullets']}/{total_b})" if sb is not None else "— by bullets"
    w = f"{sw}% by words" if sw is not None else "— by words"
    return f"{b} · {w}"


def build_labor_report(owner, entries, *, scope="all", label="", detail="summary"):
    agg = aggregate(entries)
    by_repo: dict = {}
    for e in entries:
        by_repo.setdefault(e.repo, []).append(e)
    stats = {"entries": len(entries), "projects": len(by_repo), **agg}

    lines = [f"# Division of Labor — {owner}", "", label, "", CAPTION, "",
             "## Overall",
             f"- Direction share: {_share_line(agg)}",
             f"- Decisions logged: {len(entries)} across {len(by_repo)} project(s)", ""]
    if not entries:
        lines += ["_No entries in this window._", ""]

    for repo in by_repo:
        lines.append(f"## {repo}")
        lines.append(f"- Direction share: {_share_line(aggregate(by_repo[repo]))}")
        if detail == "entries":
            for e in sorted(by_repo[repo], key=lambda x: x.date):
                s = split_entry(e)
                sh = _share(s.human_bullets, s.human_bullets + s.ai_bullets)
                sh_s = f"{sh}%" if sh is not None else "—"
                lines.append(f"  - {e.date} — {e.title}   "
                             f"{s.human_bullets}/{s.ai_bullets} bullets · {sh_s}")
        lines.append("")

    trend = monthly_trend(entries)
    if trend:
        lines.append("## Monthly trend (direction share by bullets)")
        for month, share, n in trend:
            sh_s = f"{share}%" if share is not None else "—"
            lines.append(f"- {month}: {sh_s} ({n} entr{'y' if n == 1 else 'ies'})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_labor.py -q`
Expected: PASS (all labor tests).

- [ ] **Step 5: Commit**

```bash
git add server/labor.py tests/test_labor.py
git commit -m "feat(labor): monthly_trend + build_labor_report (per-project, detail=entries)"
```

---

## Task 4: Direction-share line in the period digest

**Files:**
- Modify: `server/digest.py`
- Test: `tests/test_labor.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_labor.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_labor.py -k direction_share -v`
Expected: FAIL — `test_digest_shows_direction_share_when_bullets` fails (line absent).

- [ ] **Step 3: Implement**

In `server/digest.py`, add to the imports at the top:

```python
from server.labor import aggregate as _labor_aggregate
```

In `build_digest`, find the tools line and the firsts block in the Summary section:

```python
    if tools:
        lines.append(f"- Tools: {top(tools)}")
    if firsts_in_window:
```

Insert the Direction-share line between them, so it reads:

```python
    if tools:
        lines.append(f"- Tools: {top(tools)}")
    _la = _labor_aggregate(entries)
    if _la["share_bullets"] is not None:
        _tb = _la["human_bullets"] + _la["ai_bullets"]
        lines.append(f"- Direction share: {_la['share_bullets']}% by bullets "
                     f"({_la['human_bullets']}/{_tb}) · {_la['share_words']}% by words")
    if firsts_in_window:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_labor.py tests/test_digest.py -q`
Expected: PASS (new direction-share tests + all existing digest tests still green).

- [ ] **Step 5: Commit**

```bash
git add server/digest.py tests/test_labor.py
git commit -m "feat(digest): add omittable Direction-share line to the digest"
```

---

## Task 5: `service.division_of_labor`

**Files:**
- Modify: `server/service.py`
- Test: `tests/test_labor.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_labor.py`:

```python
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
    assert res["stats"]["share_bullets"] == 67    # 2 human / 1 ai


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
    res = svc.division_of_labor(scope="all")
    assert res["status"] == "blocked" and "alice@acme.com" in res["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_labor.py -k division_of_labor -v`
Expected: FAIL with `AttributeError: 'JournalService' object has no attribute 'division_of_labor'`.

- [ ] **Step 3: Implement**

In `server/service.py`, add near the other `from server import ...` lines:

```python
from server import labor as LB
```

Add this method (e.g. after `period_summary`):

```python
    def division_of_labor(self, *, period="month", basis="to-date", since=None, until=None,
                          scope="all", detail="summary") -> dict:
        import datetime
        scope = "work" if scope.lower() == "work" else "all"
        detail = "entries" if detail == "entries" else "summary"
        s, u, label = DG.period_window(period, basis, since, until, datetime.date.today())
        jr = self._load_journal()

        def in_scope(e):
            return scope == "all" or jr.repo_category.get(e.repo) == "Work"

        selected = [e for e in jr.entries if in_scope(e) and s <= e.date <= u]
        report, stats = LB.build_labor_report(self.cfg.owner_name, selected,
                                              scope=scope, label=label, detail=detail)
        findings = self._scan_all(report)
        if findings:
            spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
            return {"status": "blocked", "message": f"labor report blocked (customer data): {spans}."}
        return {"status": "ok", "report": report, "stats": stats}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_labor.py -q`
Expected: PASS (all labor tests, incl. the 3 integration tests).

- [ ] **Step 5: Commit**

```bash
git add server/service.py tests/test_labor.py
git commit -m "feat(service): division_of_labor — window+scope, render, egress scan"
```

---

## Task 6: Register the `division_of_labor` MCP tool

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_main_smoke.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main_smoke.py`:

```python
def test_division_of_labor_tool_registered(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        f'journal_path="{tmp_path/"DECISIONS_JOURNAL.md"}"\n'
        'repo_roots=[]\ndev_domains=["github.com"]\n'
    )
    mcp = build_server(config_path=cfg)
    assert "division_of_labor" in _tool_names(mcp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_main_smoke.py::test_division_of_labor_tool_registered -v`
Expected: FAIL — `division_of_labor` not registered.

- [ ] **Step 3: Implement**

In `server/main.py`, after the `period_summary` tool registration, add:

```python
    @mcp.tool(description=(
        "Read-only division-of-labor metric: 'direction share' = the owner's decision "
        "bullets ÷ all bullets, by bullets and words, over a window. A descriptive proxy "
        "(not effort/value). period/basis/since/until window like period_summary; "
        "scope='all'|'work'; detail='summary'|'entries' (entries adds a per-entry split). "
        "Shows overall, per-project, and a month-by-month trend."))
    def division_of_labor(period: str = "month", basis: str = "to-date",
                          since: str | None = None, until: str | None = None,
                          scope: str = "all", detail: str = "summary") -> dict:
        return svc.division_of_labor(period=period, basis=basis, since=since, until=until,
                                     scope=scope, detail=detail)
```

- [ ] **Step 4: Run the full suite to verify pass**

Run: `python3 -m pytest -q`
Expected: PASS (all, incl. the new smoke test).

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_main_smoke.py
git commit -m "feat(main): register division_of_labor tool"
```

---

## Task 7: Docs — README tool row + section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the tool row + section**

In `README.md`, add a Tools-table row (after `period_summary`):

```markdown
| `division_of_labor` | "Direction share" (your decisions ÷ all bullets), per-project + trend. |
```

And add a section before `## Privacy`:

```markdown
## Division of labor

`division_of_labor` reports **direction share** — the owner's Human-driven-decision
bullets ÷ all bullets — by bullets and words, with a per-project breakdown and a
month-by-month trend. It is a **descriptive proxy** for how much of the logged work was
the owner directing vs. the agent executing, *not* a measure of effort, value, or "who did
more"; showcasing belongs in the (separate) brags log. Window via `period`/`basis`/
`since`/`until` (like `period_summary`); `scope="work"` for sharing; `detail="entries"`
lists each entry's split. The period digest also shows a one-line direction share.
Read-only. See `docs/DIVISION-OF-LABOR.md`.
```

- [ ] **Step 2: Verify nothing broke**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the division_of_labor metric"
```

---

## Final verification

- [ ] Run the entire suite: `python3 -m pytest -q` — all green.
- [ ] Confirm read-only (no journal write, no git), the digest shows/omits the share line
  correctly, `detail="entries"` lists per-entry splits, the monthly trend groups by
  `YYYY-MM`, and the egress scan blocks customer data in a rendered report.
