# Categorization Add-on Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an opt-in, zero-core-coupling add-on that turns the blind `needs_category` ask into a guess-you-confirm for Work/Personal, learned from already-categorized repos, with the PII-bearing mapping cached outside any repo.

**Architecture:** Pure signal/guess logic in `server/categorize.py`; a self-contained `server/addons/categorization.py` that adds one MCP tool (`guess_category`) and a RULES snippet, wired in `main.py` only when `[categorization].enabled`. Core `log_decision` is untouched — the agent orchestrates guess→confirm→log. Source of truth for labels stays the private journal; the derived mapping is cached in a configurable `state_dir` outside any repo and never synced.

**Tech Stack:** Python 3.11+, FastMCP, stdlib only (`subprocess`, `json`, `dataclasses`), pytest. Reuses `server/ownership.py` + `server/gitops.py` subprocess helpers.

**Spec:** `docs/CATEGORIZATION.md`.

**Working branch:** `feature/categorization-addon` (already checked out, off `main`).

---

## File Structure

- **Create** `server/categorize.py` — pure: `Signals`, `Guess`, `guess()`, `signals_for()`.
- **Modify** `server/ownership.py` — extract `remote_owner()`; refactor `is_collaboration()` to reuse it.
- **Modify** `server/gitops.py` — add `author_email_domains()`.
- **Modify** `server/config.py` — add `categorization_enabled`, `state_dir`; parse `[categorization]`.
- **Create** `server/addons/__init__.py` — package marker.
- **Create** `server/addons/categorization.py` — `categorize_repo()`, `rules_snippet()`, `register()`, state cache.
- **Create** `server/addons/categorization.RULES.md` — agent guidance snippet.
- **Modify** `server/main.py` — conditionally append the snippet + register the tool.
- **Modify** `config.example.toml` — commented `[categorization]` block.
- **Modify** `README.md` — short "Optional add-ons" note + tool-table row.
- **Create** `tests/test_categorize.py` — pure-logic + integration + smoke tests.

Run the whole suite with `cd /tmp/hdj && . .venv/bin/activate && python3 -m pytest -q` at every "run tests" step.

---

## Task 1: `remote_owner()` helper + refactor `is_collaboration()`

**Files:**
- Modify: `server/ownership.py`
- Test: `tests/test_ownership.py` (add one test; existing tests guard the refactor)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ownership.py`:

```python
from server.ownership import remote_owner

def test_remote_owner_extracts_org(tmp_path):
    repo = tmp_path / "r"
    _make_repo(repo, "jo@x.com", "git@github.com:AcmeCorp/r.git")
    assert remote_owner(repo) == "acmecorp"

def test_remote_owner_none_without_remote(tmp_path):
    repo = tmp_path / "noremote"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert remote_owner(repo) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ownership.py::test_remote_owner_extracts_org -v`
Expected: FAIL with `ImportError: cannot import name 'remote_owner'`.

- [ ] **Step 3: Add `remote_owner` and refactor `is_collaboration`**

In `server/ownership.py`, add after `_git_out`:

```python
def remote_owner(repo_path: Path) -> str | None:
    """Owner/org segment of the repo's first available remote URL, lowercased."""
    for remote in ("upstream", "origin"):
        url = _git_out(repo_path, "remote", "get-url", remote)
        if not url:
            continue
        tail = url.split(":")[-1] if ":" in url and "//" not in url else url.split("//")[-1]
        parts = [p for p in tail.replace(":", "/").split("/") if p]
        if len(parts) >= 2:
            return parts[-2].lower()
    return None
```

Replace the remote-URL loop at the top of `is_collaboration` so it reuses the helper:

```python
def is_collaboration(repo_path: Path, owner_identities: list[str]) -> bool:
    """True when the repo's canonical ownership is NOT the owner's:
    an origin/upstream URL owner that isn't the owner, or authorship majority not-owner."""
    owners = {o.lower() for o in owner_identities}
    org = remote_owner(repo_path)
    if org is not None:
        return org not in owners
    log = _git_out(repo_path, "shortlog", "-sne", "HEAD")
    if not log:
        return False
    mine = others = 0
    for line in log.splitlines():
        count_str = line.strip().split("\t")[0]
        try:
            n = int(count_str)
        except ValueError:
            continue
        low = line.lower()
        if any(o in low for o in owners):
            mine += n
        else:
            others += n
    return others > mine
```

- [ ] **Step 4: Run the ownership suite to verify pass + no regression**

Run: `python3 -m pytest tests/test_ownership.py -v`
Expected: PASS (the 2 new tests + all pre-existing collaboration tests).

- [ ] **Step 5: Commit**

```bash
git add server/ownership.py tests/test_ownership.py
git commit -m "refactor(ownership): extract remote_owner; reuse in is_collaboration"
```

---

## Task 2: `author_email_domains()` in gitops

**Files:**
- Modify: `server/gitops.py`
- Test: `tests/test_gitops.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_gitops.py` (reuse its existing imports; if it has no repo helper, add this one):

```python
import subprocess
from server.gitops import author_email_domains

def _mk(path, email):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", email], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "f").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=path, check=True, capture_output=True)

def test_author_email_domains(tmp_path):
    repo = tmp_path / "r"
    _mk(repo, "jo@Acme.com")
    assert author_email_domains(repo) == {"acme.com": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_gitops.py::test_author_email_domains -v`
Expected: FAIL with `ImportError: cannot import name 'author_email_domains'`.

- [ ] **Step 3: Implement**

In `server/gitops.py`, add:

```python
def author_email_domains(path: Path) -> dict[str, int]:
    """Map of lowercased author-email domain -> commit count across history."""
    out = _run(Path(path), "log", "--pretty=%ae").stdout
    counts: dict[str, int] = {}
    for line in out.splitlines():
        line = line.strip()
        if "@" in line:
            dom = line.rsplit("@", 1)[1].lower()
            if dom:
                counts[dom] = counts.get(dom, 0) + 1
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_gitops.py::test_author_email_domains -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/gitops.py tests/test_gitops.py
git commit -m "feat(gitops): add author_email_domains"
```

---

## Task 3: Pure `categorize.py` — `Signals`, `Guess`, `guess()`

**Files:**
- Create: `server/categorize.py`
- Test: `tests/test_categorize.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_categorize.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_categorize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.categorize'`.

- [ ] **Step 3: Implement the pure layer**

Create `server/categorize.py` (pure logic only — `signals_for` is added in Task 4):

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Signals:
    remote_org: str | None
    email_domains: tuple[str, ...]
    path_prefix: str | None
    is_collaboration: bool


@dataclass
class Guess:
    guess: str | None        # "Work" | "Personal" | None
    confidence: str          # "high" | "medium" | "low"
    reasons: list[str]


def guess(target: Signals, labeled: list[tuple[Signals, str]]) -> Guess:
    if len(labeled) < 2:
        return Guess(None, "low", ["fewer than 2 categorized repos yet — asking directly"])

    votes = {"Work": 0, "Personal": 0}
    axes = {"Work": set(), "Personal": set()}
    reasons: list[str] = []

    def cast(axis: str, matches: list[str], reason_for):
        if not matches or len(set(matches)) != 1:
            return  # no match, or axis spans both categories -> no vote
        cat = matches[0]
        votes[cat] += len(matches)
        axes[cat].add(axis)
        reasons.append(reason_for(cat, len(matches)))

    if target.remote_org:
        m = [c for s, c in labeled if s.remote_org and s.remote_org == target.remote_org]
        cast("org", m, lambda cat, n: f"same git-host org '{target.remote_org}' as {n} {cat} repo(s)")

    if target.email_domains:
        tset = set(target.email_domains)
        m = [c for s, c in labeled if tset & set(s.email_domains)]
        shared = ", ".join(sorted(tset)[:2])
        cast("email", m, lambda cat, n: f"same author email domain ({shared}) as {n} {cat} repo(s)")

    if target.path_prefix:
        m = [c for s, c in labeled if s.path_prefix == target.path_prefix]
        cast("path", m, lambda cat, n: f"under the same folder '{target.path_prefix}' as {n} {cat} repo(s)")

    work, personal = votes["Work"], votes["Personal"]
    if work and personal:
        return Guess(None, "low", ["signals point both ways — asking directly"])
    if work == 0 and personal == 0:
        return Guess(None, "low", ["no matching categorized repos — asking directly"])
    cat = "Work" if work > personal else "Personal"
    confidence = "high" if (len(axes[cat]) >= 2 and votes[cat] >= 2) else "medium"
    return Guess(cat, confidence, reasons)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_categorize.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add server/categorize.py tests/test_categorize.py
git commit -m "feat(categorize): pure Signals + guess() voting logic"
```

---

## Task 4: `signals_for()` over a real repo

**Files:**
- Modify: `server/categorize.py` (add `signals_for` + its imports)
- Test: `tests/test_categorize.py` (add)

The `_make_repo` helper defined here is reused by Task 6's integration tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_categorize.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_categorize.py::test_signals_for_reads_repo -v`
Expected: FAIL with `ImportError: cannot import name 'signals_for' from 'server.categorize'`.

- [ ] **Step 3: Add `signals_for` to `server/categorize.py`**

Change the top imports of `server/categorize.py` from:

```python
from __future__ import annotations
from dataclasses import dataclass
```

to:

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from server import gitops
from server.ownership import remote_owner, is_collaboration
```

Then add this function directly after the `Guess` dataclass (before `def guess`):

```python
def signals_for(path, owner_identities: list[str]) -> Signals:
    p = Path(path)
    domains = tuple(sorted(gitops.author_email_domains(p).keys()))
    return Signals(
        remote_org=remote_owner(p),
        email_domains=domains,
        path_prefix=str(p.parent),
        is_collaboration=is_collaboration(p, owner_identities),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_categorize.py::test_signals_for_reads_repo -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/categorize.py tests/test_categorize.py
git commit -m "feat(categorize): add signals_for over a repo"
```

---

## Task 5: Config — `[categorization]` table

**Files:**
- Modify: `server/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_categorization_defaults_off(tmp_path):
    (tmp_path / "config.toml").write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        'journal_path="J.md"\nrepo_roots=[]\ndev_domains=["github.com"]\n'
    )
    cfg = load_config(tmp_path / "config.toml")
    assert cfg.categorization_enabled is False
    assert cfg.state_dir is not None  # defaulted

def test_categorization_enabled_with_state_dir(tmp_path):
    (tmp_path / "config.toml").write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        'journal_path="J.md"\nrepo_roots=[]\ndev_domains=["github.com"]\n'
        '[categorization]\nenabled=true\nstate_dir="~/somewhere/state"\n'
    )
    cfg = load_config(tmp_path / "config.toml")
    assert cfg.categorization_enabled is True
    assert cfg.state_dir == Path("~/somewhere/state").expanduser()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -k categorization -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'categorization_enabled'`.

- [ ] **Step 3: Implement**

In `server/config.py`, add `import os` at top. Extend the dataclass:

```python
@dataclass(frozen=True)
class Config:
    owner_name: str
    owner_identities: list[str]
    journal_path: Path
    repo_roots: list[Path]
    dev_domains: list[str]
    categorization_enabled: bool = False
    state_dir: Path | None = None
```

Add the default-resolver and extend `load_config`'s return:

```python
def _default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "state"
    return root / "human-decision-journal"
```

Inside `load_config`, before the `return`:

```python
    cat = data.get("categorization", {})
    cat_enabled = bool(cat.get("enabled", False))
    sd = cat.get("state_dir")
    state_dir = Path(sd).expanduser() if sd else _default_state_dir()
```

And add to the `Config(...)` constructor call:

```python
        categorization_enabled=cat_enabled,
        state_dir=state_dir,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS (new + existing config tests).

- [ ] **Step 5: Commit**

```bash
git add server/config.py tests/test_config.py
git commit -m "feat(config): optional [categorization] table (enabled, state_dir)"
```

---

## Task 6: The add-on module + RULES snippet

**Files:**
- Create: `server/addons/__init__.py`
- Create: `server/addons/categorization.py`
- Create: `server/addons/categorization.RULES.md`
- Test: `tests/test_categorize.py` (add integration tests)

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_categorize.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_categorize.py -k "categorize_repo or rules_snippet" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.addons'`.

- [ ] **Step 3: Create the package + RULES snippet + module**

Create `server/addons/__init__.py` (empty file).

Create `server/addons/categorization.RULES.md`:

```markdown
## Categorization add-on (Work/Personal)

When `log_decision` returns `needs_category` for a repo, do NOT ask blind first — call
`guess_category(repo)`.

- If it returns a `guess` ("Work"/"Personal"), tell the owner what it looks like and why,
  and confirm: e.g. *"This repo looks like **Work** — <reasons>. Right?"* Then re-call
  `log_decision` with the confirmed `category`. Never auto-file; always let the owner override.
- If `guess` is null (low confidence / not enough history / conflicting signals), ask
  plainly: *"Is this repo Work or Personal?"*
```

Create `server/addons/categorization.py`:

```python
from __future__ import annotations
import json
from pathlib import Path

from server.categorize import signals_for, guess, Signals
from server.ownership import resolve_repo_path

_RULES = Path(__file__).with_name("categorization.RULES.md")


def rules_snippet() -> str:
    return _RULES.read_text() if _RULES.exists() else ""


def _labeled_signals(svc) -> list[tuple[Signals, str]]:
    jr = svc._load_journal()
    out: list[tuple[Signals, str]] = []
    for repo, cat in jr.repo_category.items():
        path = resolve_repo_path(repo, svc.cfg.repo_roots)
        if path is None:
            continue
        try:
            out.append((signals_for(path, svc.cfg.owner_identities), cat))
        except Exception:
            continue
    return out


def _write_cache(cfg, labeled, target_repo, result) -> None:
    if cfg.state_dir is None:
        return
    sd = Path(cfg.state_dir)
    try:
        sd.mkdir(parents=True, exist_ok=True)
        data = {
            "labeled": [
                {"remote_org": s.remote_org, "email_domains": list(s.email_domains),
                 "path_prefix": s.path_prefix, "is_collaboration": s.is_collaboration,
                 "category": c}
                for s, c in labeled
            ],
            "last_guess": {"repo": target_repo, "guess": result.guess,
                           "confidence": result.confidence, "reasons": result.reasons},
        }
        (sd / "categories.local.json").write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def categorize_repo(svc, repo: str) -> dict:
    path = resolve_repo_path(repo, svc.cfg.repo_roots)
    if path is None:
        return {"status": "no_path", "guess": None, "confidence": "low",
                "reasons": [f"repo '{repo}' not found under repo_roots — ask Work or Personal directly"]}
    labeled = _labeled_signals(svc)
    target = signals_for(path, svc.cfg.owner_identities)
    result = guess(target, labeled)
    _write_cache(svc.cfg, labeled, repo, result)
    return {"status": "ok", "guess": result.guess,
            "confidence": result.confidence, "reasons": result.reasons}


def register(mcp, svc, cfg) -> None:
    @mcp.tool(description=(
        "Categorization add-on: guess whether a repo is Work or Personal from signals "
        "(git-host org, author email domain, folder) learned off already-categorized repos. "
        "Returns {guess, confidence, reasons}; guess may be null when uncertain. ALWAYS confirm "
        "with the owner before logging — never auto-file. Call on a needs_category response."))
    def guess_category(repo: str) -> dict:
        return categorize_repo(svc, repo)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_categorize.py -v`
Expected: PASS (all categorize tests, including the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add server/addons/__init__.py server/addons/categorization.py \
        server/addons/categorization.RULES.md tests/test_categorize.py
git commit -m "feat(addon): categorization module — guess_category, state cache, RULES"
```

---

## Task 7: Wire into `main.py` (conditional, opt-in)

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_main_smoke.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main_smoke.py`:

```python
def _write_cfg(tmp_path, extra=""):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        f'journal_path="{tmp_path/"DECISIONS_JOURNAL.md"}"\n'
        'repo_roots=[]\ndev_domains=["github.com"]\n' + extra
    )
    return cfg


def test_categorization_tool_absent_by_default(tmp_path):
    mcp = build_server(config_path=_write_cfg(tmp_path))
    assert "guess_category" not in _tool_names(mcp)


def test_categorization_tool_present_when_enabled(tmp_path):
    cfg = _write_cfg(tmp_path, "[categorization]\nenabled=true\n"
                               f'state_dir="{tmp_path/"state"}"\n')
    mcp = build_server(config_path=cfg)
    assert "guess_category" in _tool_names(mcp)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_main_smoke.py -k categorization -v`
Expected: FAIL — `test_categorization_tool_present_when_enabled` fails (`guess_category` not registered).

- [ ] **Step 3: Implement the wiring**

In `server/main.py`, replace the body of `build_server` between the `svc = ...` line and `return mcp` so it conditionally loads the add-on. Specifically, change the instructions/construction block to:

```python
    cat_addon = None
    if cfg.categorization_enabled:
        from server.addons import categorization as cat_addon

    instructions = _instructions(ROOT / "RULES.md", cfg)
    if cat_addon:
        snippet = cat_addon.rules_snippet()
        if snippet:
            instructions = instructions + "\n\n" + snippet

    mcp = FastMCP("decision-journal", instructions=instructions)
```

Then, immediately before `return mcp`, add:

```python
    if cat_addon:
        cat_addon.register(mcp, svc, cfg)

    return mcp
```

(Leave every existing `@mcp.tool` registration exactly as-is.)

- [ ] **Step 4: Run the full suite to verify pass**

Run: `python3 -m pytest -q`
Expected: PASS — all prior tests plus the 2 new smoke tests.

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_main_smoke.py
git commit -m "feat(main): conditionally register categorization add-on when enabled"
```

---

## Task 8: Docs — example config + README note

**Files:**
- Modify: `config.example.toml`
- Modify: `README.md`

- [ ] **Step 1: Add the commented config block**

Append to `config.example.toml`:

```toml

# --- Optional add-on: Work/Personal categorization -------------------------------
# Guess whether a NEW repo is Work or Personal from signals learned off your
# already-categorized repos (git-host org, author email domain, folder). You ALWAYS
# confirm; nothing is auto-filed. The PII-bearing mapping is cached in state_dir —
# OUTSIDE any repo — and is never synced. Off by default.
# [categorization]
# enabled = true
# state_dir = "~/.local/state/human-decision-journal"
```

- [ ] **Step 2: Add the README tool row + note**

In `README.md`, add a row to the Tools table (after `get_timeline`):

```markdown
| `guess_category` | (add-on) Guess Work/Personal for a new repo; you confirm. |
```

And add a short section before `## Privacy`:

```markdown
## Optional add-ons

Add-ons are opt-in modules enabled in `config.toml`; when off, they add nothing.

- **Categorization** (`[categorization] enabled = true`) — on a new repo, instead of
  asking blind, the agent guesses Work or Personal from signals learned off your already-
  categorized repos and asks you to confirm. The derived mapping contains client/employer
  identifiers, so it is cached in `state_dir` **outside any repo** and never synced. See
  `docs/CATEGORIZATION.md`.
```

- [ ] **Step 3: Verify docs render / links resolve**

Run: `python3 -m pytest -q`
Expected: PASS (no test impact; this confirms nothing broke).

- [ ] **Step 4: Commit**

```bash
git add config.example.toml README.md
git commit -m "docs: document the categorization add-on (example config + README)"
```

---

## Final verification

- [ ] **Run the entire suite**

Run: `cd /tmp/hdj && . .venv/bin/activate && python3 -m pytest -q`
Expected: all green (baseline 43 + new categorize/config/gitops/ownership/smoke tests).

- [ ] **Manual smoke of a guess** (optional sanity)

Build two temp repos under a root, log them as Work, then in a Python REPL call
`categorization.categorize_repo(svc, "<third repo>")` and confirm `guess == "Work"` with
non-empty `reasons` and a `categories.local.json` written under `state_dir`.

- [ ] **Confirm scope:** `log_decision` is unchanged; the add-on is absent unless enabled;
  no PII path is written inside the repo tree.
