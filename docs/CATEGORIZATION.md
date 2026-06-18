# Design: Categorization Add-on (guess-and-confirm Work/Personal)

## Why

Every entry is filed under **Work** or **Personal**, and that axis is load-bearing: the
authorship report is Work-only, and the coverage report's scope depends on it. Today the
category is asked **blind** on each new repo (`needs_category`). This add-on learns from
the repos you've already categorized and turns the blind ask into a **guess you confirm** —
*"This repo looks like Work (same GitHub org as 4 of your work repos) — right?"* — with a
one-keystroke override. It seeds those labels repo-by-repo during backfill.

It is **read-only** with respect to git, **never auto-files** (you always confirm), and
**opt-in** (off unless enabled in config).

## Modular add-on — zero core coupling

This is shipped as a self-contained module, not woven into the core.

- **Code:** all logic lives in `server/addons/categorization.py` (+ pure helpers in
  `server/categorize.py`). A `register(mcp, svc, cfg)` hook adds the tool.
- **One additive tool:** `guess_category(repo)`. No other tool changes.
- **The core stays untouched.** `log_decision`/`needs_category` are *not* modified. When
  the add-on is **off**, you get today's blind ask. When **on**, the agent orchestrates:
  on a `needs_category`, it calls `guess_category`, presents the guess, confirms with you,
  then re-calls `log_decision` with the confirmed `category`. The behavior is driven by a
  RULES snippet, not by core code calling into the add-on.
- **Config-gated, opt-in:**
  ```toml
  [categorization]
  enabled = true                                   # default false
  state_dir = "~/.local/state/human-decision-journal"   # optional; see below
  ```
  `main.py` only registers the tool when `enabled`. `Config` gains optional fields with
  safe defaults, so existing configs and tests are unaffected.
- **Disable = clean removal.** Flip `enabled = false` and the tool disappears; the core
  falls back to the blind ask with no residue.

This establishes a light add-on pattern (a module + a `register()` + a config table +
isolated state) that future features can follow — without a heavyweight plugin framework.

## PII state lives outside any repo

The derived mapping names clients/employers (`org acme-corp → Work`, work email domains).
That is PII and **must never enter the public engine repo** — stronger than gitignore,
because an accidental `git add -A` shouldn't be able to catch it.

- The add-on persists its mapping to **`state_dir`, a directory outside any repo**
  (default: XDG `~/.local/state/human-decision-journal/categories.local.json`).
- It is a **refreshable cache, not the source of truth.** Source of truth = the private
  journal's labels (`repo_category`, parsed from the `# Work`/`# Personal` sections) +
  live git signals. The cache can be deleted and rebuilt at any time.
- It is **never synced** — not to the engine repo's remote, not to the journal's private
  remote. It is purely local machine state.
- If `state_dir` is unset, default to the XDG path; create it on first write.

## How categories persist (no change to the journal model)

A repo's category is still recorded the moment its first entry is logged — `category`
flows in through `log_decision` and lands in the journal section, exactly as today. The
add-on adds **no new label storage in the journal**; it only *reads* those labels to learn
from, and caches the *derived mapping* in `state_dir`.

**Property:** during backfill the labeled set grows as you go, so the guesser starts cold
(blind asks) and gets more confident with each confirmation.

## Signals (deterministic, rule-based — not ML)

With a handful of repos there is nothing to "train"; we extract the signals that separate
the repos you already labeled. All reachable via the existing subprocess helpers:

- **Remote owner org** — `github.com/<org>/…`. Already parsed inside
  `ownership.is_collaboration()`; extract a small `remote_owner(path)` helper to reuse it.
- **Author email domain(s)** — `git log --pretty=%ae`, domain part; work vs personal mail.
- **Path prefix** under `repo_roots` — e.g. `~/work/…` vs `~/projects/…`.
- **is_collaboration** — available as one weak input (collaboration ≠ Work; an OSS repo you
  contribute to is collaboration but Personal).

`signals_for(path, identities)` → `{remote_org, email_domains, path_prefix,
is_collaboration}` is pure and testable.

## Confidence model + always-confirm

Each available signal "votes" by matching the target against already-labeled repos.

- **High** — ≥2 signals agree, backed by ≥2 labeled examples.
- **Medium** — one signal, or thin support.
- **Low / none** — signals conflict, or fewer than ~2 labels exist → **fall back to a
  blind ask.**

Confidence only changes the **wording**; the add-on **always confirms** and never
auto-files:
- confident → *"This repo looks like **Work** (same org as 4 work repos) — right?"*
- low → *"New repo — Work or Personal?"* (today's behavior)

`guess(target, labeled)` → `{guess: "Work"|"Personal"|None, confidence:
"high"|"medium"|"low", reasons: [str]}`.

## The freelancer case is the north star

For a salaried dev, remote-org cleanly splits work from personal. For a **freelancer**
(client work and personal projects under one account and one email), that signal
collapses. So the design makes **path-prefix and per-repo confirmation first-class** and
**degrades to a blind ask on conflict** rather than guessing wrong and training reflexive
confirmation. This is the canonical low-confidence example and a tested scenario.

## Privacy

- Signals and reason strings (which may name a client org) are surfaced **only to the
  owner, locally, in the confirm prompt**. The journal stores only the final
  `Work`/`Personal` — never a reason, org, or email domain.
- Reason strings must never be passed into an entry; a test asserts this.
- The PII-bearing mapping lives only in `state_dir`, outside any repo, never synced.

## Components / files

- `server/categorize.py` — pure: `signals_for(...)`, `guess(...)`. No I/O.
- `server/addons/categorization.py` — `register(mcp, svc, cfg)`; the `guess_category`
  service logic (load journal labels → resolve paths → signals → guess); the `state_dir`
  cache read/write/refresh.
- `server/ownership.py` — extract `remote_owner(path)` from the existing remote-parsing.
- `server/gitops.py` — add `author_email_domains(path, since=None)`.
- `server/config.py` — optional `[categorization]` table → `categorization_enabled: bool`,
  `state_dir: Path | None` (defaults applied in `load_config`).
- `server/main.py` — `if cfg.categorization_enabled: register(mcp, svc, cfg)`.
- `server/addons/categorization.RULES.md` — the agent instruction (on `needs_category`
  with the add-on present: `guess_category` → present → confirm → re-`log_decision`).
  `register()` appends this snippet to the server's FastMCP `instructions` **only when the
  add-on is enabled**, so core `RULES.md` is never edited and the guidance is absent when
  the add-on is off.
- `config.example.toml` — commented `[categorization]` block.
- `tests/test_categorize.py` — temp repos with controlled remotes / author emails / paths;
  a seeded labeled set; assert signal extraction, guess + confidence + reasons,
  **cold-start → blind ask**, **conflicting signals → low confidence**, `state_dir` cache
  written outside the repo, and **reason strings never reach the journal**.

## Out of scope (YAGNI)

- The broader transcript-mining backfill engine (separate, larger feature). This add-on
  provides the categorization *the backfill driver calls*, not the mining.
- Any ML / training.
- A general plugin framework — one module + `register()` + config table is enough.
- Auto-categorization without confirmation.
- Storing employer identity anywhere but the local, out-of-repo `state_dir`.
