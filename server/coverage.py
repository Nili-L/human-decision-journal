from __future__ import annotations
from dataclasses import dataclass, field

LEVELS = ("headline", "summary", "detailed", "full")


@dataclass
class RepoCoverage:
    repo: str
    category: str | None          # "Work" | "Personal" | None (uncategorized)
    active: set                   # date strings with an owner commit
    logged: set                   # date strings with a journal entry
    subjects: dict = field(default_factory=dict)   # date -> [subject], only at full

    @property
    def active_days(self) -> int:
        return len(self.active)

    @property
    def documented_days(self) -> int:
        return len(self.active & self.logged)

    @property
    def gap_days(self) -> list[str]:
        return sorted(self.active - self.logged)

    @property
    def coverage(self) -> int:
        return round(100 * self.documented_days / self.active_days) if self.active_days else 0


def _label(rc: RepoCoverage) -> str:
    return rc.category or "uncategorized"


def build_report(owner: str, repos: list[RepoCoverage], *, scope: str = "all",
                 level: str = "summary") -> tuple[str, dict]:
    rank = LEVELS.index(level) if level in LEVELS else 1
    active_total = sum(r.active_days for r in repos)
    documented_total = sum(r.documented_days for r in repos)
    overall = round(100 * documented_total / active_total) if active_total else 0
    all_dates = sorted(d for r in repos for d in r.active)
    window = f"{all_dates[0]} → {all_dates[-1]}" if all_dates else "no activity in range"

    stats = {"repos": len(repos), "active_days": active_total,
             "documented_days": documented_total, "coverage_pct": overall,
             "since": all_dates[0] if all_dates else None,
             "until": all_dates[-1] if all_dates else None}

    lines = [f"# Coverage — {owner}", "", f"{window} · scope: {scope}", "",
             "## Summary",
             f"- overall: {overall}% of active days documented ({documented_total}/{active_total})"]

    if scope == "all":
        for cat in ("Work", "Personal"):
            sub = [r for r in repos if r.category == cat]
            if sub:
                a = sum(r.active_days for r in sub)
                d = sum(r.documented_days for r in sub)
                pct = round(100 * d / a) if a else 0
                lines.append(f"- {cat}: {pct}% ({d}/{a})")
    lines.append("")

    if not repos:
        lines += ["_No active repos in range._", ""]

    if rank >= 1:  # summary and deeper
        for r in repos:
            lines.append(f"## {r.repo} [{_label(r)}]")
            lines.append(f"- active days: {r.active_days} · documented: "
                         f"{r.documented_days} · coverage: {r.coverage}%")
            if rank >= 2 and r.gap_days:  # detailed and deeper
                lines.append(f"- gap days: {', '.join(r.gap_days)}")
                if rank >= 3:  # full
                    for d in r.gap_days:
                        subs = "; ".join(r.subjects.get(d, []))
                        lines.append(f"    {d}  {subs}".rstrip())
            lines.append("")

    return "\n".join(lines).rstrip() + "\n", stats
