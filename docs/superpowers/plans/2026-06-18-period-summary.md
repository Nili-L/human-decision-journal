# Period Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only `period_summary` MCP tool that rolls a time window of journal entries into a digest (counts, top tags, in-window firsts, per-project titles or full decision bullets).

**Architecture:** Pure date-math + render in `server/digest.py`; `JournalService.period_summary` selects entries by window + scope, computes in-window firsts via `timeline.firsts()`, renders, and egress-scans. Registered as a core read tool in `main.py`. Reuses `report.py` for the `detail="full"` bullet extraction.

**Tech Stack:** Python 3.11+, FastMCP, stdlib (`datetime`, `calendar`, `collections`), pytest.

**Spec:** `docs/PERIOD-SUMMARY.md`. **Branch:** `feature/period-summary` (checked out, off `main`).

Run the suite at each gate: `cd /tmp/hdj && . .venv/bin/activate && python3 -m pytest -q`.

---

## File Structure

- **Modify** `server/report.py` — add public `human_decision_bullets(raw)` (wraps existing `_sections`/`_bullets`).
- **Create** `server/digest.py` — `period_window(...)` + `build_digest(...)` (pure).
- **Modify** `server/service.py` — `period_summary(...)`.
- **Modify** `server/main.py` — register the `period_summary` tool.
- **Create** `tests/test_digest.py` — window math, render, integration.

---

## Task 1: `human_decision_bullets` helper in report.py

**Files:**
- Modify: `server/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
from server.report import human_decision_bullets

def test_human_decision_bullets_extracts():
    raw = ("### 2026-06-01 — t\n\n**Session focus:** f\n\n"
           "**Human-driven decisions:**\n- chose A\n- set bar B\n\n"
           "**AI execution:**\n- did X\n\n**Tags:** domain: backend · activity: design\n")
    assert human_decision_bullets(raw) == ["- chose A", "- set bar B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_report.py::test_human_decision_bullets_extracts -v`
Expected: FAIL with `ImportError: cannot import name 'human_decision_bullets'`.

- [ ] **Step 3: Implement**

In `server/report.py`, add after the `_bullets` function:

```python
def human_decision_bullets(raw: str) -> list[str]:
    """The owner's Human-driven decision bullets (each '- '-prefixed) from a rendered entry."""
    return _bullets(_sections(raw).get("**Human-driven decisions:**", []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_report.py::test_human_decision_bullets_extracts -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/report.py tests/test_report.py
git commit -m "feat(report): public human_decision_bullets() helper"
```

---

## Task 2: `period_window` (pure date math)

**Files:**
- Create: `server/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_digest.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.digest'`.

- [ ] **Step 3: Implement**

Create `server/digest.py`:

```python
from __future__ import annotations
import calendar as _cal
from datetime import date, timedelta

PERIODS = ("week", "month", "quarter")
BASES = ("rolling", "calendar", "to-date", "previous")


def _sub_months(d: date, n: int) -> date:
    m = d.month - 1 - n
    y = d.year + m // 12
    m = m % 12 + 1
    last = _cal.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _sunday_start(d: date) -> date:
    # Python weekday(): Mon=0..Sun=6; days since most recent Sunday:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _quarter_first(d: date) -> date:
    qm = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, qm, 1)


def period_window(period: str, basis: str, since, until, today: date):
    """Return (since_iso, until_iso, label). since/until (either set) override period/basis."""
    if since is not None or until is not None:
        s = since or "0001-01-01"
        u = until or today.isoformat()
        return s, u, f"{s} → {u}"

    if period not in PERIODS:
        period = "month"
    if basis not in BASES:
        basis = "to-date"

    if period == "week":
        if basis in ("rolling", "calendar"):
            s, u = today - timedelta(days=6), today
        elif basis == "to-date":
            s, u = _sunday_start(today), today
        else:  # previous full Sun–Sat week
            u = _sunday_start(today) - timedelta(days=1)
            s = u - timedelta(days=6)
    elif period == "month":
        if basis == "rolling":
            s, u = today - timedelta(days=29), today
        elif basis == "calendar":
            s, u = _sub_months(today, 1) + timedelta(days=1), today
        elif basis == "to-date":
            s, u = today.replace(day=1), today
        else:  # previous full calendar month
            u = today.replace(day=1) - timedelta(days=1)
            s = u.replace(day=1)
    else:  # quarter
        if basis == "rolling":
            s, u = today - timedelta(days=89), today
        elif basis == "calendar":
            s, u = _sub_months(today, 3) + timedelta(days=1), today
        elif basis == "to-date":
            s, u = _quarter_first(today), today
        else:  # previous full quarter
            u = _quarter_first(today) - timedelta(days=1)
            s = _quarter_first(u)

    si, ui = s.isoformat(), u.isoformat()
    return si, ui, f"{basis} {period} · {si} → {ui}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add server/digest.py tests/test_digest.py
git commit -m "feat(digest): period_window date math (4 bases, Sunday weeks)"
```

---

## Task 3: `build_digest` (pure render)

**Files:**
- Modify: `server/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_digest.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_digest.py -k "digest_summary or full_detail or empty_window" -v`
Expected: FAIL with `ImportError: cannot import name 'build_digest'`.

- [ ] **Step 3: Implement**

In `server/digest.py`, add at the top with the other imports:

```python
from collections import Counter

from server.report import human_decision_bullets
```

Then add at the end of the file:

```python
def build_digest(owner, entries, firsts_in_window, *, scope="all",
                 label="", detail="titles"):
    by_repo: dict = {}
    for e in entries:
        by_repo.setdefault(e.repo, []).append(e)
    domains = Counter(d for e in entries for d in e.domains)
    activities = Counter(a for e in entries for a in e.activities)
    tools = Counter(t for e in entries for t in e.tools)
    stats = {"entries": len(entries), "projects": len(by_repo),
             "domains": dict(domains), "activities": dict(activities)}

    def top(c, n=5):
        return ", ".join(f"{k} ({v})" for k, v in c.most_common(n))

    lines = [f"# Digest — {owner}", "", label, "", "## Summary",
             f"- Decisions logged: {len(entries)} across {len(by_repo)} project(s)"]
    if domains:
        lines.append(f"- Domains: {top(domains)}")
    if activities:
        lines.append(f"- Activities: {top(activities)}")
    if tools:
        lines.append(f"- Tools: {top(tools)}")
    if firsts_in_window:
        fl = ", ".join(sorted(f"{axis}: {value}" for (_d, axis, value, _r) in firsts_in_window))
        lines.append(f"- New firsts: {fl}")
    lines.append("")

    if not entries:
        lines += ["_No entries in this window._", ""]

    for repo in by_repo:
        lines.append(f"## {repo}")
        for e in sorted(by_repo[repo], key=lambda x: x.date):
            lines.append(f"- {e.date} — {e.title}")
            if detail == "full":
                for b in human_decision_bullets(e.raw):
                    text = b[2:] if b.startswith("- ") else b
                    lines.append(f"  - {text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest.py -q`
Expected: PASS (all digest tests).

- [ ] **Step 5: Commit**

```bash
git add server/digest.py tests/test_digest.py
git commit -m "feat(digest): build_digest render (summary, titles/full, firsts)"
```

---

## Task 4: `service.period_summary`

**Files:**
- Modify: `server/service.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_digest.py`:

```python
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
    # A window entirely in the past excludes today's entry.
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
    # Title with a customer email: log_decision would normally block it, so write a raw
    # entry directly to prove the digest's own egress scan also catches it.
    svc.log_decision(repo="portal", category="work", title="clean", **_LOG)
    jr = svc._load_journal()
    jr.entries[0].title = "ping alice@acme.com"
    import server.journal as J
    J.write_atomic(svc.cfg.journal_path, J.render(jr, svc._vocab()))
    res = svc.period_summary(scope="all")
    assert res["status"] == "blocked"
    assert "alice@acme.com" in res["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_digest.py -k period_summary -v`
Expected: FAIL with `AttributeError: 'JournalService' object has no attribute 'period_summary'`.

- [ ] **Step 3: Implement**

In `server/service.py`, add near the other `from server import ...` lines:

```python
from server import digest as DG
```

Add this method (e.g. after `coverage_report`):

```python
    def period_summary(self, *, period="month", basis="to-date", since=None, until=None,
                       scope="all", detail="titles") -> dict:
        import datetime
        scope = "work" if scope.lower() == "work" else "all"
        detail = "full" if detail == "full" else "titles"
        s, u, label = DG.period_window(period, basis, since, until, datetime.date.today())
        jr = self._load_journal()

        def in_scope(e):
            return scope == "all" or jr.repo_category.get(e.repo) == "Work"

        scoped = [e for e in jr.entries if in_scope(e)]
        selected = [e for e in scoped if s <= e.date <= u]
        firsts_in_window = [f for f in firsts(scoped) if s <= f[0] <= u]
        report, stats = DG.build_digest(self.cfg.owner_name, selected, firsts_in_window,
                                        scope=scope, label=label, detail=detail)
        findings = self._scan_all(report)
        if findings:
            spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
            return {"status": "blocked", "message": f"digest blocked (customer data): {spans}."}
        return {"status": "ok", "digest": report, "stats": stats}
```

(`firsts` is already imported in `service.py` via `from server.timeline import build_timeline, firsts`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest.py -q`
Expected: PASS (all digest tests, incl. the 4 integration tests).

- [ ] **Step 5: Commit**

```bash
git add server/service.py tests/test_digest.py
git commit -m "feat(service): period_summary — window+scope selection, in-window firsts, egress scan"
```

---

## Task 5: Register the `period_summary` MCP tool

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_main_smoke.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main_smoke.py`:

```python
def test_period_summary_tool_registered(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        f'journal_path="{tmp_path/"DECISIONS_JOURNAL.md"}"\n'
        'repo_roots=[]\ndev_domains=["github.com"]\n'
    )
    mcp = build_server(config_path=cfg)
    assert "period_summary" in _tool_names(mcp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_main_smoke.py::test_period_summary_tool_registered -v`
Expected: FAIL — `period_summary` not registered.

- [ ] **Step 3: Implement**

In `server/main.py`, after the `coverage_report` tool registration, add:

```python
    @mcp.tool(description=(
        "Read-only period digest: roll a time window of journal entries into a summary "
        "(decisions, projects, top tags, new 'firsts'). period='week'|'month'|'quarter'; "
        "basis='rolling'(fixed 7/30/90d)|'calendar'(exact 1wk/1mo/3mo)|'to-date'|'previous'; "
        "since/until ('YYYY-MM-DD') override. scope='all'|'work'. detail='titles'|'full' "
        "(full includes each entry's Human-driven decision bullets)."))
    def period_summary(period: str = "month", basis: str = "to-date",
                       since: str | None = None, until: str | None = None,
                       scope: str = "all", detail: str = "titles") -> dict:
        return svc.period_summary(period=period, basis=basis, since=since, until=until,
                                  scope=scope, detail=detail)
```

- [ ] **Step 4: Run the full suite to verify pass**

Run: `python3 -m pytest -q`
Expected: PASS (all, incl. the new smoke test).

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_main_smoke.py
git commit -m "feat(main): register period_summary tool"
```

---

## Task 6: Docs — README tool row + section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the tool row + section**

In `README.md`, add a Tools-table row (after `coverage_report`):

```markdown
| `period_summary` | Digest a week/month/quarter of entries; counts, top tags, firsts. |
```

And add a section before `## Privacy`:

```markdown
## Period digest

`period_summary` rolls a time window of entries into a digest — decisions, projects, top
domains/activities/tools, and new "firsts" — for a standup, a manager update, or
self-review. Pick the window with `period` (`week`/`month`/`quarter`) × `basis`
(`rolling` = last 7/30/90 days, `calendar` = exact 1 week/month/quarter, `to-date`,
`previous`), or pass `since`/`until`. Weeks start Sunday. `scope="work"` limits it for
sharing; `detail="full"` includes each entry's Human-driven decision bullets. Read-only.
See `docs/PERIOD-SUMMARY.md`.
```

- [ ] **Step 2: Verify nothing broke**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the period_summary digest tool"
```

---

## Final verification

- [ ] Run the entire suite: `python3 -m pytest -q` — all green.
- [ ] Confirm `period_summary` is read-only (no journal write, no git), the 4 bases produce
  the expected windows, `detail="full"` surfaces Human-driven bullets, and the egress scan
  blocks customer data in a rendered digest.
