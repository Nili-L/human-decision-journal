"""Authorship Report: a read-only, work-scoped evidentiary export of the journal.

The journal is a private growth mirror (Work + Personal, candid, never written for an
audience). This module derives a *shareable* view from it that answers one question for
a manager or client: on this project, what did the owner decide and what did the agent
do? It selects entries and reformats their existing human/AI split — it never writes the
journal and never touches git. See docs/AUTHORSHIP-REPORT.md.
"""
from __future__ import annotations
from collections import Counter

from server.journal import Journal, Entry

_LABELS = (
    "**Session focus:**",
    "**Human-driven decisions:**",
    "**AI execution:**",
    "**Notable artifacts:**",
    "**Source:**",
    "**Tags:**",
)


def _sections(raw: str) -> dict[str, list[str]]:
    """Split a rendered entry's raw markdown into its labelled blocks.

    Returns a map from label -> list of body lines (bullets keep their '- ' prefix).
    Entries are produced by a fixed renderer, so the labels are stable.
    """
    out: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        matched = next((lbl for lbl in _LABELS if stripped.startswith(lbl)), None)
        if matched:
            current = matched
            inline = stripped[len(matched):].strip()
            out[current] = [inline] if inline else []
        elif current and stripped:
            out[current].append(stripped)
    return out


def _bullets(lines: list[str]) -> list[str]:
    """Normalise a block's lines to bullet strings (drop empties, keep one '- ' each)."""
    items = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        items.append(l if l.startswith("- ") else f"- {l}")
    return items


def select(journal: Journal, *, category: str = "Work",
           since: str | None = None, until: str | None = None,
           repos: list[str] | None = None) -> list[Entry]:
    cat = "Work" if category.lower() == "work" else "Personal"
    repo_filter = set(repos) if repos else None
    picked = []
    for e in journal.entries:
        if e.category != cat:
            continue
        if since and e.date < since:
            continue
        if until and e.date > until:
            continue
        if repo_filter is not None and e.repo not in repo_filter:
            continue
        picked.append(e)
    return picked


def _tag_line(e: Entry) -> str:
    parts = []
    if e.domains:
        parts.append("domain: " + ", ".join(e.domains))
    if e.activities:
        parts.append("activity: " + ", ".join(e.activities))
    if e.tools:
        parts.append("tools: " + ", ".join(e.tools))
    return " · ".join(parts)


def build_report(journal: Journal, owner_name: str, *, category: str = "Work",
                 since: str | None = None, until: str | None = None,
                 repos: list[str] | None = None) -> tuple[str, dict]:
    """Render an authorship report. Returns (markdown, stats)."""
    entries = select(journal, category=category, since=since, until=until, repos=repos)
    cat = "Work" if category.lower() == "work" else "Personal"

    by_repo: dict[str, list[Entry]] = {}
    for e in entries:
        by_repo.setdefault(e.repo, []).append(e)

    dates = sorted(e.date for e in entries)
    domain_counts = Counter(d for e in entries for d in e.domains)
    activity_counts = Counter(a for e in entries for a in e.activities)
    stats = {
        "entries": len(entries),
        "projects": len(by_repo),
        "since": dates[0] if dates else None,
        "until": dates[-1] if dates else None,
    }

    window = f"{dates[0]} → {dates[-1]}" if dates else "no entries in range"
    lines = [
        f"# Authorship Report — {owner_name}",
        "",
        f"{window} · scope: {cat}",
        "",
        "> Each entry separates **my decisions** (mine) from **agent execution** (the"
        " AI's), recorded at the time the work was done. This is a filtered export of a"
        " private decisions journal; personal projects are excluded.",
        "",
        "## Summary",
        f"- Decisions logged: {len(entries)} across {len(by_repo)} project(s)",
        f"- Window: {window}",
    ]
    if domain_counts:
        top_d = ", ".join(f"{d} ({n})" for d, n in domain_counts.most_common(5))
        lines.append(f"- Domains: {top_d}")
    if activity_counts:
        top_a = ", ".join(f"{a} ({n})" for a, n in activity_counts.most_common(5))
        lines.append(f"- Activities: {top_a}")
    lines.append("")

    if not entries:
        lines += ["_No entries match this scope._", ""]

    for repo in by_repo:
        lines.append(f"## {repo}")
        blurb = journal.repo_blurb.get(repo, "")
        if blurb:
            lines += ["", blurb]
        for e in sorted(by_repo[repo], key=lambda x: x.date):
            sec = _sections(e.raw)
            mine = _bullets(sec.get("**Human-driven decisions:**", []))
            agent = _bullets(sec.get("**AI execution:**", []))
            lines += ["", f"### {e.date} — {e.title}", "", "**My decisions:**"]
            lines += mine or ["- (none recorded)"]
            lines += ["", "**Agent execution:**"]
            lines += agent or ["- (none recorded)"]
            tag_line = _tag_line(e)
            if tag_line:
                lines += ["", f"**Tags:** {tag_line}"]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
