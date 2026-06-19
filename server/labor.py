from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

from server.report import human_decision_bullets, ai_execution_bullets

CAPTION = ("> Direction share is a *descriptive proxy* for how much of the logged work was "
           "the owner directing vs. the agent executing — not a measure of effort, value, "
           'or "who did more."')


@dataclass
class Split:
    human_bullets: int
    ai_bullets: int
    human_words: int
    ai_words: int


def _text(b: str) -> str:
    return b[2:] if b.startswith("- ") else b


def _words(bullets) -> int:
    return sum(len(_text(b).split()) for b in bullets)


def split_entry(entry) -> Split:
    h = human_decision_bullets(entry.raw)
    a = ai_execution_bullets(entry.raw)
    return Split(len(h), len(a), _words(h), _words(a))


def _share(human: int, total: int):
    return round(100 * human / total) if total else None


def aggregate(entries) -> dict:
    hb = ab = hw = aw = 0
    for e in entries:
        s = split_entry(e)
        hb += s.human_bullets
        ab += s.ai_bullets
        hw += s.human_words
        aw += s.ai_words
    return {"human_bullets": hb, "ai_bullets": ab, "human_words": hw, "ai_words": aw,
            "share_bullets": _share(hb, hb + ab), "share_words": _share(hw, hw + aw)}


def monthly_trend(entries):
    by_month = defaultdict(list)
    for e in entries:
        by_month[e.date[:7]].append(e)
    out = []
    for month in sorted(by_month):
        out.append((month, aggregate(by_month[month])["share_bullets"], len(by_month[month])))
    return out


def _share_line(agg) -> str:
    sb, sw = agg["share_bullets"], agg["share_words"]
    total_b = agg["human_bullets"] + agg["ai_bullets"]
    b = f"{sb}% by bullets ({agg['human_bullets']}/{total_b})" if sb is not None else "— by bullets"
    w = f"{sw}% by words" if sw is not None else "— by words"
    return f"{b} · {w}"


def build_labor_report(owner, entries, *, scope="all", label="", detail="summary"):
    agg = aggregate(entries)
    by_repo: dict = {}
    for e in entries:
        by_repo.setdefault(e.repo, []).append(e)
    stats = {"entries": len(entries), "projects": len(by_repo), **agg}

    lines = [f"# Division of Labor — {owner}", "", label, "", CAPTION, "",
             "## Overall",
             f"- Direction share: {_share_line(agg)}",
             f"- Decisions logged: {len(entries)} across {len(by_repo)} project(s)", ""]
    if not entries:
        lines += ["_No entries in this window._", ""]

    for repo in by_repo:
        lines.append(f"## {repo}")
        lines.append(f"- Direction share: {_share_line(aggregate(by_repo[repo]))}")
        if detail == "entries":
            for e in sorted(by_repo[repo], key=lambda x: x.date):
                s = split_entry(e)
                sh = _share(s.human_bullets, s.human_bullets + s.ai_bullets)
                sh_s = f"{sh}%" if sh is not None else "—"
                lines.append(f"  - {e.date} — {e.title}   "
                             f"{s.human_bullets}/{s.ai_bullets} bullets · {sh_s}")
        lines.append("")

    trend = monthly_trend(entries)
    if trend:
        lines.append("## Monthly trend (direction share by bullets)")
        for month, share, n in trend:
            sh_s = f"{share}%" if share is not None else "—"
            lines.append(f"- {month}: {sh_s} ({n} entr{'y' if n == 1 else 'ies'})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
