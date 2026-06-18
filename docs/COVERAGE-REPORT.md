# Design: Coverage Report

## Why

The journal records the decisions you *chose* to log. It cannot, by itself, tell you
what you **didn't** log. The question a manager (or you, honestly) asks — *"what did your
work time actually go into?"* — is answered far better by reconciling the journal against
the ground truth of your git history than by the entries alone.

`coverage_report` walks your commits, compares them to the journal, and shows where work
happened without a logged decision. It is a **discipline tool first** (catch your own
logging gaps) and a **credibility signal second** (an honest "I document N% of my active
days" you can choose to share).

It is **read-only**: it walks `git log`, never writes the journal, never touches a remote.

## What it measures

Granularity is the **active day** (not the commit — the journal's own stance is that not
every commit is a decision, so a per-commit gap metric would cry wolf).

- **Active day** — a day with ≥1 commit *authored by the owner* (git author matched to
  `owner_identities`; collaborators' commits don't count toward or against you).
- **Documented day** — an active day that also has ≥1 journal entry for that repo.
- **Coverage** = documented days ÷ active days (per repo, and aggregated).
- **Gap day** — an active day with no entry for that repo: you worked, you didn't log.

## Disclosure ladder

Private by default. The caller chooses how much to reveal via `level`. Each rung is a
superset of the one above.

| `level` | Reveals | Intended reader |
|---|---|---|
| `headline` | Overall coverage % only (+ Work % / Personal % when scope=all). No repo names. | Anyone |
| `summary` | Per-repo: active days, documented days, coverage %. Repo names; no dates. | A breakdown you'll share |
| `detailed` | + the gap-day **dates** per repo. | Your own review / a trusted lead |
| `full` | + commit **subjects** on gap days, all repos incl. personal. | Completely private |

`scope`: `all` (default — includes Personal repos) or `work` (Work repos only, for sharing).

## Tool signature

```
coverage_report(since: str | None = None,
                until: str | None = None,
                scope: str = "all",         # "all" | "work"
                level: str = "summary")     # "headline" | "summary" | "detailed" | "full"
  -> {status, report, stats}
```
`since`/`until` are inclusive `YYYY-MM-DD`. Omit for all-time.

## Data flow

1. **Discover repos.** Walk `repo_roots`; each immediate subdirectory that is a git repo
   is a candidate. Its directory basename is the repo key (the same name `log_decision`
   records).
2. **Active dates.** Per repo, `git log` in `[since, until]`, read each commit's author
   identity + author date (`--date=short`). Keep dates whose author matches
   `owner_identities` (email or name substring, reusing the matching `ownership.py`
   already does). Collect the set of dates, and — for `full` — the subject per date.
3. **Logged dates.** Parse the journal; per repo, collect the set of entry dates.
4. **Compute.** active, documented = active ∩ logged, coverage, gap days = active − logged.
   Aggregate overall and by Work/Personal (category comes from the journal's repo→category
   map). A git repo absent from the journal is **uncategorized** — and a repo you committed
   to but *never logged* is the most important gap to see. So: under `scope="all"`
   (private default) uncategorized active repos **are shown** (as 0%-coverage rows — that's
   how you discover them); under `scope="work"` only repos categorized **Work** appear, so
   the shared view stays clean (an uncategorized repo surfaces in your private `all` view,
   where you'd notice it and either log it or let it get categorized).
5. **Render** at `level`, honoring `scope`.
6. **Privacy scan** the rendered text (see below); return `{status, report, stats}`.

## Privacy

Every rendered level passes through the same `privacy.scan` used elsewhere.

- `headline` / `summary` / `detailed` emit only numbers, dates, and repo names — no
  free-form external prose — so they are inherently clean.
- `full` is the only level that pulls in commit **subjects** (author-written text that may
  name a customer). There, matched spans are **redacted inline** (masked, e.g. `███`)
  rather than blocking the whole report. Rationale: `full` is explicitly the private rung;
  redaction preserves its signal ("you worked here, didn't log it") while guaranteeing raw
  customer data never appears in output. This is the one deliberate departure from the
  journal's strict hard-block, justified by the level being private-only.
- **Residual, unchanged from today:** a repo whose *name* is a client's company name is a
  by-habit concern; pattern-matching can't catch names in prose. `scope="work"` plus the
  owner's naming discipline manage it, same as the journal itself.

## Limitation (documented, not fixed)

Matching is by **date**. It assumes an entry's date is the day the work happened — true
under the commit-trigger model. Entries **backfilled** later (dated to the work, logged
afterward) match fine; entries dated to the logging day rather than the work day could
read as gaps. Acceptable: "committed that day, logged nothing" is exactly the signal.

## Boundaries / components

Mirrors the authorship-report feature's layering.

- `server/coverage.py` — pure compute + render. `build_coverage(active_by_repo,
  logged_by_repo, categories, *, scope, level)` → `(markdown, stats)`. No I/O.
- `server/gitops.py` — add `list_git_repos(roots)` and `owner_commit_dates(path,
  identities, since, until, with_subjects=False)`. Subprocess, matching existing style.
- `server/service.py` — `coverage_report(...)`: orchestrate discovery → git → journal →
  compute → render → egress scan. Returns the dict.
- `server/main.py` — register the `coverage_report` MCP tool.
- `tests/test_coverage.py` — build a temp git repo, commit as the owner and as a stranger
  on fixed dates (`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`), seed matching/non-matching
  journal entries, and assert: owner-commit filtering, active-day detection, the coverage
  math, gap-day lists, each disclosure level's contents, `scope` filtering, and
  `full`-level redaction of a planted customer email in a commit subject.

## Out of scope (YAGNI)

- No write path, no git mutation, no network.
- No commit-message body (subjects only, and only at `full`).
- No charts/HTML — markdown only (a visual dashboard is a separate, later idea).
- No time-of-day or line-count effort weighting — active *day* is the unit.
