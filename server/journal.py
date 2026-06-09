from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

from server.timeline import build_timeline

TOC_START, TOC_END = "<!-- TOC:START -->", "<!-- TOC:END -->"
TL_START, TL_END = "<!-- TIMELINE:START -->", "<!-- TIMELINE:END -->"

DEFAULT_HEADER = """# Decisions Journal

A private journal of the decisions you make while building software: what you decided and why, kept separate from what the AI did. A mirror for your growth, not a portfolio.

**How it works:** an MCP server maintains this across whatever AI tool you use. On *commit* the agent logs locally; on *push* the journal syncs to its private remote. Every entry is tagged by **domain** (what part of the system) and **activity** (what kind of work). The server keeps a **Timeline of firsts** so you can see yourself stretching. A privacy guard hard-blocks customer data.

**Examples:** "Designed the schema for new analytics tables" -> domain: database, activity: design. "Tracked down a race condition" -> domain: backend, activity: debugging.

**Reading guard:** this is private, not a showcase. Metrics exist only to keep attribution honest; the load-bearing content of every entry is the human-driven decisions.
"""

@dataclass
class Entry:
    date: str
    title: str
    repo: str
    category: str
    domains: list[str]
    activities: list[str]
    tools: list[str]
    raw: str = ""

@dataclass
class Journal:
    header: str
    entries: list[Entry] = field(default_factory=list)
    repo_category: dict[str, str] = field(default_factory=dict)
    repo_order: dict[str, list[str]] = field(default_factory=dict)

CATEGORIES = ("Work", "Personal")
_ENTRY_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}) — (.*)$")
_TAGS_RE = re.compile(r"^\*\*Tags:\*\* (.*)$")

def new_journal_text() -> str:
    j = Journal(header=DEFAULT_HEADER)
    return render(j, vocab=None)

def render_entry(e: Entry) -> str:
    if e.raw:
        return e.raw
    tags = f"domain: {', '.join(e.domains)} · activity: {', '.join(e.activities)}"
    if e.tools:
        tags += f" · tools: {', '.join(e.tools)}"
    return (
        f"### {e.date} — {e.title}\n\n"
        f"**Tags:** {tags}\n"
    )

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def _render_toc(j: Journal) -> str:
    lines = [TOC_START, "## Table of Contents"]
    for cat in CATEGORIES:
        repos = j.repo_order.get(cat, [])
        if not repos:
            continue
        lines.append(f"- **{cat}**")
        for r in repos:
            lines.append(f"  - [{r}](#{_slug(r)})")
    lines.append(TOC_END)
    return "\n".join(lines)

def render(j: Journal, vocab=None) -> str:
    parts = [j.header.rstrip() + "\n", _render_toc(j), ""]
    parts.append(TL_START)
    parts.append(build_timeline(j.entries))
    parts.append(TL_END)
    parts.append("")
    for cat in CATEGORIES:
        repos = j.repo_order.get(cat, [])
        if not repos:
            continue
        parts.append(f"# {cat}\n")
        for r in repos:
            parts.append(f"## {r}\n")
            for e in [e for e in j.entries if e.repo == r]:
                parts.append(render_entry(e).rstrip() + "\n")
    return "\n".join(parts).rstrip() + "\n"

def _parse_tags(line: str):
    domains, activities, tools = [], [], []
    body = _TAGS_RE.match(line).group(1)
    for seg in body.split("·"):
        seg = seg.strip()
        if seg.startswith("domain:"):
            domains = [t.strip() for t in seg[len("domain:"):].split(",") if t.strip()]
        elif seg.startswith("activity:"):
            activities = [t.strip() for t in seg[len("activity:"):].split(",") if t.strip()]
        elif seg.startswith("tools:"):
            tools = [t.strip() for t in seg[len("tools:"):].split(",") if t.strip()]
    return domains, activities, tools

def parse(text: str) -> Journal:
    head, _, rest = text.partition(TOC_START)
    j = Journal(header=head.rstrip() + "\n")
    after_tl = rest.partition(TL_END)[2] if TL_END in rest else rest.partition(TOC_END)[2]
    lines = after_tl.splitlines()
    cat = None
    repo = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# ") and line[2:].strip() in CATEGORIES:
            cat = line[2:].strip()
        elif line.startswith("## "):
            repo = line[3:].strip()
            if repo and cat:
                j.repo_category[repo] = cat
                j.repo_order.setdefault(cat, [])
                if repo not in j.repo_order[cat]:
                    j.repo_order[cat].append(repo)
        elif _ENTRY_RE.match(line):
            m = _ENTRY_RE.match(line)
            block = [line]
            j_i = i + 1
            while j_i < len(lines) and not (lines[j_i].startswith("### ")
                  or (lines[j_i].startswith("## "))
                  or (lines[j_i].startswith("# ") and lines[j_i][2:].strip() in CATEGORIES)):
                block.append(lines[j_i]); j_i += 1
            domains = activities = tools = []
            for bl in block:
                if _TAGS_RE.match(bl):
                    domains, activities, tools = _parse_tags(bl)
            j.entries.append(Entry(
                date=m.group(1), title=m.group(2), repo=repo or "", category=cat or "Work",
                domains=domains, activities=activities, tools=tools,
                raw="\n".join(block).rstrip() + "\n",
            ))
            i = j_i - 1
        i += 1
    return j

def write_atomic(path: Path, text: str) -> None:
    import os, tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
