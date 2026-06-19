from __future__ import annotations
import calendar as _cal
from collections import Counter
from datetime import date, timedelta

from server.report import human_decision_bullets
from server.labor import aggregate as _labor_aggregate

PERIODS = ("week", "month", "quarter")
BASES = ("rolling", "calendar", "to-date", "previous")


def _sub_months(d: date, n: int) -> date:
    m = d.month - 1 - n
    y = d.year + m // 12
    m = m % 12 + 1
    last = _cal.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _sunday_start(d: date) -> date:
    # Python weekday(): Mon=0..Sun=6; days since most recent Sunday:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _quarter_first(d: date) -> date:
    qm = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, qm, 1)


def period_window(period: str, basis: str, since, until, today: date):
    """Return (since_iso, until_iso, label). since/until (either set) override period/basis."""
    if since is not None or until is not None:
        s = since or "0001-01-01"
        u = until or today.isoformat()
        return s, u, f"{s} → {u}"

    if period not in PERIODS:
        period = "month"
    if basis not in BASES:
        basis = "to-date"

    if period == "week":
        if basis in ("rolling", "calendar"):
            s, u = today - timedelta(days=6), today
        elif basis == "to-date":
            s, u = _sunday_start(today), today
        else:  # previous full Sun–Sat week
            u = _sunday_start(today) - timedelta(days=1)
            s = u - timedelta(days=6)
    elif period == "month":
        if basis == "rolling":
            s, u = today - timedelta(days=29), today
        elif basis == "calendar":
            s, u = _sub_months(today, 1) + timedelta(days=1), today
        elif basis == "to-date":
            s, u = today.replace(day=1), today
        else:  # previous full calendar month
            u = today.replace(day=1) - timedelta(days=1)
            s = u.replace(day=1)
    else:  # quarter
        if basis == "rolling":
            s, u = today - timedelta(days=89), today
        elif basis == "calendar":
            s, u = _sub_months(today, 3) + timedelta(days=1), today
        elif basis == "to-date":
            s, u = _quarter_first(today), today
        else:  # previous full quarter
            u = _quarter_first(today) - timedelta(days=1)
            s = _quarter_first(u)

    si, ui = s.isoformat(), u.isoformat()
    return si, ui, f"{basis} {period} · {si} → {ui}"


def build_digest(owner, entries, firsts_in_window, *, scope="all",
                 label="", detail="titles"):
    by_repo: dict = {}
    for e in entries:
        by_repo.setdefault(e.repo, []).append(e)
    domains = Counter(d for e in entries for d in e.domains)
    activities = Counter(a for e in entries for a in e.activities)
    tools = Counter(t for e in entries for t in e.tools)
    stats = {"entries": len(entries), "projects": len(by_repo),
             "domains": dict(domains), "activities": dict(activities)}

    def top(c, n=5):
        return ", ".join(f"{k} ({v})" for k, v in c.most_common(n))

    lines = [f"# Digest — {owner}", "", label, "", "## Summary",
             f"- Decisions logged: {len(entries)} across {len(by_repo)} project(s)"]
    if domains:
        lines.append(f"- Domains: {top(domains)}")
    if activities:
        lines.append(f"- Activities: {top(activities)}")
    if tools:
        lines.append(f"- Tools: {top(tools)}")
    _la = _labor_aggregate(entries)
    if _la["share_bullets"] is not None:
        _tb = _la["human_bullets"] + _la["ai_bullets"]
        lines.append(f"- Direction share: {_la['share_bullets']}% by bullets "
                     f"({_la['human_bullets']}/{_tb}) · {_la['share_words']}% by words")
    if firsts_in_window:
        fl = ", ".join(sorted(f"{axis}: {value}" for (_d, axis, value, _r) in firsts_in_window))
        lines.append(f"- New firsts: {fl}")
    lines.append("")

    if not entries:
        lines += ["_No entries in this window._", ""]

    for repo in by_repo:
        lines.append(f"## {repo}")
        for e in sorted(by_repo[repo], key=lambda x: x.date):
            lines.append(f"- {e.date} — {e.title}")
            if detail == "full":
                for b in human_decision_bullets(e.raw):
                    text = b[2:] if b.startswith("- ") else b
                    lines.append(f"  - {text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
