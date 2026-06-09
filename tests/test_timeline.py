from server.timeline import build_timeline, firsts
from dataclasses import dataclass

@dataclass
class FakeEntry:
    date: str
    repo: str
    domains: list
    activities: list
    tools: list

def E(date, repo, domains, activities, tools=()):
    return FakeEntry(date=date, repo=repo, domains=list(domains),
                     activities=list(activities), tools=list(tools))

def test_firsts_only_first_occurrence():
    entries = [
        E("2026-01-01", "a", ["backend"], ["design"], ["fastmcp"]),
        E("2026-02-01", "b", ["backend"], ["debugging"]),   # backend already seen
    ]
    f = firsts(entries)
    values = {(axis, value) for _, axis, value, _ in f}
    assert ("domain", "backend") in values
    assert ("activity", "design") in values
    assert ("activity", "debugging") in values
    assert ("tool", "fastmcp") in values
    assert sum(1 for _, axis, v, _ in f if axis == "domain" and v == "backend") == 1

def test_tool_only_first_has_no_dangling_separator():
    entries = [
        E("2026-01-01", "a", ["backend"], ["design"]),
        E("2026-02-01", "a", ["backend"], ["design"], ["fastmcp"]),  # only the tool is new
    ]
    text = build_timeline(entries)
    assert "- 2026-02-01 — a — tools: fastmcp" in text
    assert "—  —" not in text

def test_rollup_counts_every_entry():
    entries = [
        E("2026-01-01", "a", ["backend"], ["design"]),
        E("2026-02-01", "a", ["backend"], ["debugging"]),
    ]
    text = build_timeline(entries)
    assert "backend (2)" in text
    assert "design (1)" in text and "debugging (1)" in text
    assert "## Firsts" in text and "## What I do most" in text
