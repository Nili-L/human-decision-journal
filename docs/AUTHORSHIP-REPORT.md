# Design: Authorship Report Export

## Why

The journal is a **private mirror** — a complete, candid record kept for the owner's
own growth, spanning Work *and* Personal repos. It is deliberately *not* a portfolio
(see the Reading guard in the journal header).

But the same entries answer a separate, real question: **"on this project, what did
*I* decide, and what did the agent do?"** — the question a manager or client asks when
work is AI-assisted. Answering it honestly is hard to do after the fact and easy to
dispute. The journal already captures it at decision time, with the human contribution
and the AI execution recorded separately and in the owner's own words.

The Authorship Report turns that private record into a **shareable, work-scoped
evidentiary artifact** without compromising the journal.

## The record/report split (why this preserves the journal)

| | Journal (the record) | Authorship Report (the report) |
|---|---|---|
| Audience | The owner, private | A manager / client, on request |
| Scope | Everything (Work + Personal) | **Work only**, optionally narrowed |
| Purpose | Growth mirror | Attribution evidence |
| Written | Continuously, at decision time | **Generated on demand** from the record |

The journal is **never written for an audience** — that is what keeps it honest (the
Reading guard). The report is a *derived view*, produced from entries that already
exist, so generating it cannot make the journal performative. You get the honesty
*and* the receipts.

## Tool: `export_authorship_report`

A read-only export. It never writes the journal and never touches git.

**Parameters**
- `category` (default `"work"`) — which section to draw from. Personal is excluded by
  default; a report is for the owner's employer/clients, not their private projects.
- `since`, `until` (optional, `YYYY-MM-DD`) — inclusive date window. Omit for all-time.
- `repos` (optional list) — narrow to specific projects (e.g. a single client repo).

**Behavior**
1. Load and parse the journal (or the configured `journal_path`).
2. Select entries: matching `category`, within `[since, until]`, in `repos` if given.
3. Render a report (see shape below): a header stating it's owner-authored, a summary
   tally, then per project each entry's **My decisions** vs **Agent execution** split.
4. **Egress privacy scan.** Re-run the customer-data scan over the *rendered report*
   before returning it. Entries are scanned at write time, but the report is the thing
   that leaves the building, so it is scanned again at the door. On any finding, block
   and return nothing — same hard-block contract as `log_decision`.
5. Return `{status, report, stats}`. The caller can save or share the markdown.

**Report shape**
```
# Authorship Report — <owner>
<date window> · generated <date> · scope: Work

> Each entry separates **my decisions** (mine) from **agent execution** (the AI's),
> recorded at the time the work was done. This is a filtered export of a private
> decisions journal; personal projects are excluded.

## Summary
- Decisions logged: N across M projects
- Window: <first> → <last>
- Most frequent: domains …, activities …

## <project>
### <date> — <title>
**My decisions:** …
**Agent execution:** …
**Tags:** domain … · activity …
```

## Out of scope (deliberately)
- No new MCP write path, no git operations — export is read-only.
- No change to the journal header's "private mirror, not a portfolio" stance; that
  remains true *of the journal*. The report is the separate surface.
- No HTML/PDF rendering — markdown only; downstream tooling can convert.
