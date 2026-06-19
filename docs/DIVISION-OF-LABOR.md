# Design: Division-of-Labor Metric

## Why

Every entry already records the owner's decisions and the agent's execution separately.
`division_of_labor` turns that into a **descriptive number** — how much of the logged work
is *direction* (the owner's decisions) versus *execution* (the agent's) — and trends it
over time. It answers a skeptic's "are you actually directing this, or just prompting?"
with evidence drawn from the record itself.

It is **read-only**: parses the journal, never writes it, never touches git.

## The honesty frame (load-bearing)

The metric is **"direction share"** = the owner's Human-driven-decision bullets ÷ all
bullets (decision + execution). It is reported **by bullets and by words, side by side**,
so neither reads as definitive, and it is **captioned** wherever it appears:

> Direction share is a *descriptive proxy* for how much of the logged work was the owner
> directing vs. the agent executing — not a measure of effort, value, or "who did more."

Per the journal's Reading guard, metrics exist to keep attribution honest, not to brag;
accomplishment framing belongs in the separate brags/wins log (a later feature), not here.

## Core — `server/labor.py` (pure, no I/O)

- `split_entry(entry)` → `{human_bullets, ai_bullets, human_words, ai_words}`. Bullet
  counts come from `report.human_decision_bullets(entry.raw)` and a new
  `report.ai_execution_bullets(entry.raw)`; word counts are the whitespace-split word
  totals of those bullet texts.
- `aggregate(entries)` → totals plus `share_bullets` and `share_words` (each a 0–100 int =
  human ÷ (human + agent); `None` when that denominator is 0 — **zero-guarded**, never
  divides by 0).
- `monthly_trend(entries)` → `[(month, share_bullets, n_entries), …]` grouped by the
  entry date's `YYYY-MM`, chronological.
- `build_labor_report(owner, entries, *, scope, label, detail)` → `(markdown, stats)`:
  the caption, overall share (bullets + words), a per-project breakdown, and the
  month-by-month trend. `detail="entries"` additionally lists each entry's own split.

## Surface 1 — digest line (fills the period_summary seam)

`digest.build_digest` gains one Summary line computed via `labor.aggregate`:

```
- Direction share: 60% by bullets (18/30) · 62% by words
```

It is **omitted when the windowed entries carry no bullets** (e.g. synthetic test entries
with empty `raw`), so existing digest tests stay green and the line never shows `0/0`.

## Surface 2 — standalone tool

```
division_of_labor(period="month", basis="to-date", since=None, until=None,
                  scope="all", detail="summary")
  -> {status, report, stats}
```

- Window: reuses `digest.period_window(period, basis, since, until, today)` — identical
  semantics to `period_summary` (4 bases, Sunday weeks, `since`/`until` override).
- `scope`: `all` (default) or `work`, same as the other read tools.
- `detail`: `summary` (default — overall + per-project + trend) or `entries` (adds a line
  per entry with its own split, e.g. `- 2026-06-18 — Chose token-remap   3/2 bullets · 60%`).
- Read-only; the rendered report passes the same `privacy.scan` egress check before return.

## Components

- **Create** `server/labor.py` — the pure functions above.
- **Modify** `server/report.py` — add `ai_execution_bullets(raw)` (mirror of
  `human_decision_bullets`).
- **Modify** `server/digest.py` — `build_digest` adds the omittable Direction-share line.
- **Modify** `server/service.py` — `division_of_labor(...)`: window → select by date+scope
  → `build_labor_report` → egress scan.
- **Modify** `server/main.py` — register the `division_of_labor` tool.
- **Create** `tests/test_labor.py` — `split_entry` counts; `aggregate` math + zero-guard
  (no bullets → `None`, no crash); `monthly_trend`; per-project + `detail="entries"`
  rendering; the digest Direction-share line appearing (entries with raw) and omitted
  (entries without); `service.division_of_labor` window/scope selection; egress scan blocks
  planted customer data in a rendered report.

## Out of scope (YAGNI / deferred)

- **Charts / HTML** — the later visual-dashboard feature.
- **Brags / wins log** — step 3 on the build-up ladder; its own spec. This metric stays
  purely descriptive and does not add any "win" marker.
- **Per-bullet weighting / NLP** — bullets and words are deliberately crude, explainable
  proxies; no attempt to score bullet "importance".
