# Design: Period Summary (digest)

## Why

The journal accumulates dated, tagged entries; `period_summary` rolls a time window of
them into a **digest** — what you worked on, across which projects, with which kinds of
work, and what you did for the first time. It answers the standup / manager-update /
self-review question "what did I get done this week/month?" without re-reading the journal.

It is **read-only**: parses the journal, never writes it, never touches git.

## Tool signature

```
period_summary(period="month", basis="to-date", since=None, until=None,
               scope="all", detail="titles")
  -> {status, digest, stats}
```

## Window model

Two small knobs cover every useful window; `since`/`until` override both.

- **`period`** — granularity: `week` | `month` | `quarter`.
- **`basis`** — which window of that granularity, relative to *today*:
  - `rolling` — a fixed day-count ending today: **7 / 30 / 90 days** for week / month / quarter.
  - `calendar` — an **exact calendar length** ending today: 7 days / 1 calendar month /
    3 calendar months. The inclusive window runs from the day after one-unit-ago through
    today (e.g. month, today=2026-06-18 → `2026-05-19 → 2026-06-18`). Differs from `rolling`
    only for month/quarter, whose real length varies.
  - `to-date` — the current calendar week / month / quarter, from its start through today.
  - `previous` — the last *complete* calendar week / month / quarter (e.g. "write up the
    month that just ended").
- **`since` / `until`** (`YYYY-MM-DD`, inclusive) — if either is given, they define the
  window and `period`/`basis` are ignored; the label becomes the literal range.

"Today" comes from the server (`datetime.date.today()`, already used in `log_decision`).
**Calendar weeks start Sunday** (Israeli Sun–Thu work week). Each window produces a human
label for the digest heading (e.g. `June 2026`, `week of 2026-06-14`, `2026-05-19 → 2026-06-18`).

## Content

The digest has a summary block then a per-project section.

- **Summary:** decisions logged, projects touched, the window label; top domains /
  activities / tools by count (top 5 each); **new "firsts" this period** — firsts whose
  date falls in the window, via `timeline.firsts()`.
- **Per project:** one subsection per repo with at least one entry in the window.
  - `detail="titles"` (default) — the entry titles only (scannable).
  - `detail="full"` — each entry's full `**Human-driven decisions:**` bullets inline,
    extracted from `Entry.raw` (reusing the section-splitter already in `report.py`).
    The bullets already exist verbatim in the journal; this surfaces them in the digest.

`scope`: `all` (default — personal self-review, includes Personal repos) or `work`
(Work repos only, for sharing) — same semantics as the other read tools.

## Privacy

The rendered digest passes through the same `privacy.scan` egress check as the other
read tools before returning; on any finding, return a `blocked` status. Titles and
bullets come from already-scanned entries, so this is defense-in-depth, but it keeps the
"nothing leaves unscanned" invariant uniform across every shareable output.

## Components

Mirrors the `coverage.py` / `report.py` layering.

- **`server/digest.py`** — pure, no I/O, fully unit-testable:
  - `period_window(period, basis, since, until, today)` → `(since, until, label)`.
  - `build_digest(owner, entries, firsts_in_window, *, scope, label, detail)` →
    `(markdown, stats)`.
- **`server/report.py`** — reuse its entry-section extractor for `detail="full"` (export
  the existing helper rather than duplicate it).
- **`server/service.py`** — `period_summary(...)`: compute window → select entries by
  date + scope → compute in-window firsts via `timeline.firsts()` → render → egress scan.
- **`server/main.py`** — register the `period_summary` MCP tool.
- **`tests/test_digest.py`** — `period_window` for each `period`×`basis` (12 combos: 3
  periods × 4 bases, with Sunday week start) + `since`/`until` override; entry selection
  by date and scope; top-N tag rollup; in-window firsts; both `detail` levels;
  empty-window digest; egress scan blocks planted data.

## Out of scope (YAGNI / deferred)

- **Human-vs-agent ratio** — that's the next feature (division-of-labor metric); it will
  plug a ratio line into this digest later. Not computed here.
- **Charts / HTML** — markdown only (visual dashboard is a later feature).
- **Trend-over-time across multiple periods** — single-window digest only for now.
