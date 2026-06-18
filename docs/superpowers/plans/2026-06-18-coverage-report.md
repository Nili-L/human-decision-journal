# Coverage Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only `coverage_report` tool that reconciles owner-authored git commits against logged journal entries, by active day, with a private-by-default disclosure ladder.

**Architecture:** New git helpers (`list_git_repos`, `owner_commit_dates`) feed a pure compute/render module (`server/coverage.py`). A `JournalService.coverage_report()` orchestrates discovery → git → journal → scope filter → render, redacts commit subjects at the `full` level via `privacy.redact`, and runs an egress scan at shareable levels. Registered as a core tool in `main.py`.

**Tech Stack:** Python 3.11+, FastMCP, stdlib (`subprocess`, `dataclasses`), pytest. Reuses `server/gitops.py`, `server/privacy.py`.

**Spec:** `docs/COVERAGE-REPORT.md`. **Branch:** `feature/coverage-report` (checked out, off `main`).

Run the suite at each gate: `cd /tmp/hdj && . .venv/bin/activate && python3 -m pytest -q`.

---

## File Structure

- **Modify** `server/gitops.py` — add `list_git_repos(roots)` and `owner_commit_dates(...)`.
- **Modify** `server/privacy.py` — add `redact(text, owner_identities, dev_domains)`.
- **Create** `server/coverage.py` — `RepoCoverage`, `build_report()` (pure).
- **Modify** `server/service.py` — `coverage_report(...)`.
- **Modify** `server/main.py` — register the `coverage_report` tool.
- **Create** `tests/test_coverage.py` — git helpers, pure render, integration.

---

## Task 1: git helpers — `list_git_repos`, `owner_commit_dates`

**Files:**
- Modify: `server/gitops.py`
- Test: `tests/test_gitops.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gitops.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_gitops.py -k "list_git_repos or owner_commit_dates" -v`
Expected: FAIL with `ImportError: cannot import name 'list_git_repos'`.

- [ ] **Step 3: Implement**

In `server/gitops.py`, add:

```python
def list_git_repos(roots) -> list[tuple[str, Path]]:
    """Immediate subdirectories of each root that are git repos: (name, path)."""
    found: list[tuple[str, Path]] = []
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and is_git_repo(child):
                found.append((child.name, child))
    return found


def owner_commit_dates(path, identities, since=None, until=None, with_subjects=False):
    """Author-dates (YYYY-MM-DD) of commits authored by the owner, optionally within
    [since, until] inclusive. with_subjects=True -> {date: [subject, ...]} else a set."""
    owners = {o.lower() for o in identities}
    out = _run(Path(path), "log", "--date=short", "--pretty=%ad%x09%ae%x09%an%x09%s").stdout
    dates_with: dict[str, list[str]] = {}
    dates: set[str] = set()
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 3:
            continue
        date, email, name = parts[0], parts[1], parts[2]
        subject = parts[3] if len(parts) > 3 else ""
        if since and date < since:
            continue
        if until and date > until:
            continue
        hay = (email + " " + name).lower()
        if not any(o in hay for o in owners):
            continue
        if with_subjects:
            dates_with.setdefault(date, []).append(subject)
        else:
            dates.add(date)
    return dates_with if with_subjects else dates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_gitops.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/gitops.py tests/test_gitops.py
git commit -m "feat(gitops): list_git_repos + owner_commit_dates"
```

---

## Task 2: `privacy.redact`

**Files:**
- Modify: `server/privacy.py`
- Test: `tests/test_privacy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_privacy.py`:

```python
from server.privacy import redact

def test_redact_masks_findings():
    text = "email alice@acme.com and ZD-9981"
    out = redact(text, ["jo@x.com"], ["github.com"])
    assert "alice@acme.com" not in out
    assert "ZD-9981" not in out
    assert "[redacted]" in out

def test_redact_keeps_clean_text():
    assert redact("just plain words", ["jo@x.com"], ["github.com"]) == "just plain words"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_privacy.py -k redact -v`
Expected: FAIL with `ImportError: cannot import name 'redact'`.

- [ ] **Step 3: Implement**

In `server/privacy.py`, add at the end:

```python
def redact(text: str, owner_identities: list[str], dev_domains: list[str]) -> str:
    """Replace every detected customer-data span with [redacted]. Reuses scan();
    splices from the end so earlier offsets stay valid."""
    findings = scan(text, owner_identities, dev_domains)
    for f in sorted(findings, key=lambda f: f.start, reverse=True):
        text = text[:f.start] + "[redacted]" + text[f.end:]
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_privacy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/privacy.py tests/test_privacy.py
git commit -m "feat(privacy): add redact() built on scan()"
```

---

## Task 3: Pure `coverage.py` — `RepoCoverage` + `build_report`

**Files:**
- Create: `server/coverage.py`
- Test: `tests/test_coverage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coverage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.coverage'`.

- [ ] **Step 3: Implement**

Create `server/coverage.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field

LEVELS = ("headline", "summary", "detailed", "full")


@dataclass
class RepoCoverage:
    repo: str
    category: str | None          # "Work" | "Personal" | None (uncategorized)
    active: set                   # date strings with an owner commit
    logged: set                   # date strings with a journal entry
    subjects: dict = field(default_factory=dict)   # date -> [subject], only at full

    @property
    def active_days(self) -> int:
        return len(self.active)

    @property
    def documented_days(self) -> int:
        return len(self.active & self.logged)

    @property
    def gap_days(self) -> list[str]:
        return sorted(self.active - self.logged)

    @property
    def coverage(self) -> int:
        return round(100 * self.documented_days / self.active_days) if self.active_days else 0


def _label(rc: RepoCoverage) -> str:
    return rc.category or "uncategorized"


def build_report(owner: str, repos: list[RepoCoverage], *, scope: str = "all",
                 level: str = "summary") -> tuple[str, dict]:
    rank = LEVELS.index(level) if level in LEVELS else 1
    active_total = sum(r.active_days for r in repos)
    documented_total = sum(r.documented_days for r in repos)
    overall = round(100 * documented_total / active_total) if active_total else 0
    all_dates = sorted(d for r in repos for d in r.active)
    window = f"{all_dates[0]} → {all_dates[-1]}" if all_dates else "no activity in range"

    stats = {"repos": len(repos), "active_days": active_total,
             "documented_days": documented_total, "coverage_pct": overall,
             "since": all_dates[0] if all_dates else None,
             "until": all_dates[-1] if all_dates else None}

    lines = [f"# Coverage — {owner}", "", f"{window} · scope: {scope}", "",
             "## Summary",
             f"- overall: {overall}% of active days documented ({documented_total}/{active_total})"]

    if scope == "all":
        for cat in ("Work", "Personal"):
            sub = [r for r in repos if r.category == cat]
            if sub:
                a = sum(r.active_days for r in sub)
                d = sum(r.documented_days for r in sub)
                pct = round(100 * d / a) if a else 0
                lines.append(f"- {cat}: {pct}% ({d}/{a})")
    lines.append("")

    if not repos:
        lines += ["_No active repos in range._", ""]

    if rank >= 1:  # summary and deeper
        for r in repos:
            lines.append(f"## {r.repo} [{_label(r)}]")
            lines.append(f"- active days: {r.active_days} · documented: "
                         f"{r.documented_days} · coverage: {r.coverage}%")
            if rank >= 2 and r.gap_days:  # detailed and deeper
                lines.append(f"- gap days: {', '.join(r.gap_days)}")
                if rank >= 3:  # full
                    for d in r.gap_days:
                        subs = "; ".join(r.subjects.get(d, []))
                        lines.append(f"    {d}  {subs}".rstrip())
            lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_coverage.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add server/coverage.py tests/test_coverage.py
git commit -m "feat(coverage): pure RepoCoverage + build_report disclosure ladder"
```

---

## Task 4: `service.coverage_report()`

**Files:**
- Modify: `server/service.py`
- Test: `tests/test_coverage.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_coverage.py`:

```python
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
    svc, roots = _svc(tmp_path)
    repo = roots / "portal"; _init(repo)
    for d in ("2026-06-01", "2026-06-02", "2026-06-03"):
        _commit(repo, d, "work")
    # Log a decision dated to one of the active days, for repo 'portal' as Work.
    svc.log_decision(repo="portal", category="work", title="t", **_LOG)
    # The entry's date is today; align one active day to today so it counts as documented.
    import datetime
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_coverage.py -k "coverage_counts or scope_work or full_level" -v`
Expected: FAIL with `AttributeError: 'JournalService' object has no attribute 'coverage_report'`.

- [ ] **Step 3: Implement**

In `server/service.py`, add `from server import coverage as CV` near the other `from server import ...` imports. Add this method (e.g. after `get_timeline`):

```python
    def coverage_report(self, *, since: str | None = None, until: str | None = None,
                        scope: str = "all", level: str = "summary") -> dict:
        scope = "work" if scope.lower() == "work" else "all"
        level = level if level in CV.LEVELS else "summary"
        jr = self._load_journal()
        logged: dict[str, set] = {}
        for e in jr.entries:
            logged.setdefault(e.repo, set()).add(e.date)
        want_subjects = (level == "full")
        repos: list[CV.RepoCoverage] = []
        for name, path in gitops.list_git_repos(self.cfg.repo_roots):
            active = gitops.owner_commit_dates(path, self.cfg.owner_identities,
                                               since=since, until=until,
                                               with_subjects=want_subjects)
            active_dates = set(active.keys()) if want_subjects else active
            if not active_dates:
                continue
            category = jr.repo_category.get(name)
            if scope == "work" and category != "Work":
                continue
            subjects = {}
            if want_subjects:
                subjects = {d: [redact_subject(s, self.cfg) for s in subs]
                            for d, subs in active.items()}
            repos.append(CV.RepoCoverage(repo=name, category=category,
                                         active=active_dates, logged=logged.get(name, set()),
                                         subjects=subjects))
        report, stats = CV.build_report(self.cfg.owner_name, repos, scope=scope, level=level)
        if level != "full":
            findings = self._scan_all(report)
            if findings:
                spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
                return {"status": "blocked",
                        "message": f"coverage report blocked (customer data): {spans}."}
        return {"status": "ok", "report": report, "stats": stats}
```

And add this module-level helper at the bottom of `server/service.py`:

```python
def redact_subject(subject: str, cfg) -> str:
    from server.privacy import redact
    return redact(subject, cfg.owner_identities, cfg.dev_domains)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_coverage.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add server/service.py tests/test_coverage.py
git commit -m "feat(service): coverage_report — discovery, scope, full-level redaction"
```

---

## Task 5: Register the `coverage_report` MCP tool

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_main_smoke.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main_smoke.py`:

```python
def test_coverage_tool_registered(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        f'journal_path="{tmp_path/"DECISIONS_JOURNAL.md"}"\n'
        'repo_roots=[]\ndev_domains=["github.com"]\n'
    )
    mcp = build_server(config_path=cfg)
    assert "coverage_report" in _tool_names(mcp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_main_smoke.py::test_coverage_tool_registered -v`
Expected: FAIL — `coverage_report` not registered.

- [ ] **Step 3: Implement**

In `server/main.py`, after the `get_timeline` tool registration, add:

```python
    @mcp.tool(description=(
        "Read-only coverage report: reconcile your own git commits against logged journal "
        "entries, by active day. Private by default. level='headline'|'summary'|'detailed'|"
        "'full' (increasing disclosure); scope='all' (incl. personal) or 'work'. Optional "
        "since/until ('YYYY-MM-DD', inclusive). Commit subjects appear only at 'full' and are "
        "redacted for customer data."))
    def coverage_report(since: str | None = None, until: str | None = None,
                        scope: str = "all", level: str = "summary") -> dict:
        return svc.coverage_report(since=since, until=until, scope=scope, level=level)
```

- [ ] **Step 4: Run the full suite to verify pass**

Run: `python3 -m pytest -q`
Expected: PASS (all, incl. the new smoke test).

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_main_smoke.py
git commit -m "feat(main): register coverage_report tool"
```

---

## Task 6: Docs — README tool row + section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the tool row + section**

In `README.md`, add a Tools-table row (after `get_timeline`):

```markdown
| `coverage_report` | Reconcile git commits vs logged entries by active day; private by default. |
```

And add a section before `## Privacy`:

```markdown
## Coverage report

`coverage_report` answers "what did my time actually go into?" by reconciling your own
git commits against logged entries, **by active day** (a day you committed but logged
nothing is a gap). It is read-only and **private by default**, with a disclosure ladder:
`headline` (one number) → `summary` (per-repo %) → `detailed` (+ gap dates) → `full`
(+ commit subjects, redacted for customer data). `scope="work"` limits it to Work repos
for sharing; `scope="all"` (default) includes everything and surfaces never-logged repos.
See `docs/COVERAGE-REPORT.md`.
```

- [ ] **Step 2: Verify nothing broke**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the coverage report tool"
```

---

## Final verification

- [ ] Run the entire suite: `python3 -m pytest -q` — all green.
- [ ] Confirm `coverage_report` is read-only (no journal write, no git mutation) and that
  `full`-level subjects are redacted while `headline`/`summary`/`detailed` emit no commit text.
