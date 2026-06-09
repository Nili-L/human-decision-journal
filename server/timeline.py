from __future__ import annotations
from collections import Counter


def firsts(entries) -> list[tuple[str, str, str, str]]:
    """Return (date, axis, value, repo) for the first occurrence of each
    domain / activity / tool, in chronological order."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, str, str]] = []
    for e in sorted(entries, key=lambda x: (x.date, x.repo)):
        for axis, values in (("domain", e.domains), ("activity", e.activities), ("tool", e.tools)):
            for v in values:
                key = (axis, v)
                if key not in seen:
                    seen.add(key)
                    out.append((e.date, axis, v, e.repo))
    return out


def build_timeline(entries) -> str:
    lines = ["# Timeline", "", "## Firsts"]
    if not entries:
        lines.append("_No entries yet._")
    else:
        from itertools import groupby
        fs = firsts(entries)
        for (date, repo), grp in groupby(fs, key=lambda t: (t[0], t[3])):
            grp = list(grp)
            doms = [v for _, a, v, _ in grp if a == "domain"]
            acts = [v for _, a, v, _ in grp if a == "activity"]
            tools = [v for _, a, v, _ in grp if a == "tool"]
            seg = []
            if doms: seg.append("domain: " + ", ".join(doms))
            if acts: seg.append("activity: " + ", ".join(acts))
            line = f"- {date} — " + " · ".join(seg) + f" — {repo}"
            if tools:
                line += f" — tools: {', '.join(tools)}"
            lines.append(line)
    dom_counts = Counter(d for e in entries for d in e.domains)
    act_counts = Counter(a for e in entries for a in e.activities)
    lines += ["", "## What I do most"]
    lines.append("Domains: " + " · ".join(f"{k} ({v})" for k, v in dom_counts.most_common()) if dom_counts else "Domains: —")
    lines.append("Activities: " + " · ".join(f"{k} ({v})" for k, v in act_counts.most_common()) if act_counts else "Activities: —")
    return "\n".join(lines)
