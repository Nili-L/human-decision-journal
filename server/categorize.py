from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Signals:
    remote_org: str | None
    email_domains: tuple[str, ...]
    path_prefix: str | None
    is_collaboration: bool


@dataclass
class Guess:
    guess: str | None        # "Work" | "Personal" | None
    confidence: str          # "high" | "medium" | "low"
    reasons: list[str]


def guess(target: Signals, labeled: list[tuple[Signals, str]]) -> Guess:
    if len(labeled) < 2:
        return Guess(None, "low", ["fewer than 2 categorized repos yet — asking directly"])

    votes = {"Work": 0, "Personal": 0}
    axes = {"Work": set(), "Personal": set()}
    reasons: list[str] = []

    def cast(axis: str, matches: list[str], reason_for):
        if not matches or len(set(matches)) != 1:
            return  # no match, or axis spans both categories -> no vote
        cat = matches[0]
        votes[cat] += len(matches)
        axes[cat].add(axis)
        reasons.append(reason_for(cat, len(matches)))

    if target.remote_org:
        m = [c for s, c in labeled if s.remote_org and s.remote_org == target.remote_org]
        cast("org", m, lambda cat, n: f"same git-host org '{target.remote_org}' as {n} {cat} repo(s)")

    if target.email_domains:
        tset = set(target.email_domains)
        m = [c for s, c in labeled if tset & set(s.email_domains)]
        shared = ", ".join(sorted(tset)[:2])
        cast("email", m, lambda cat, n: f"same author email domain ({shared}) as {n} {cat} repo(s)")

    if target.path_prefix:
        m = [c for s, c in labeled if s.path_prefix == target.path_prefix]
        cast("path", m, lambda cat, n: f"under the same folder '{target.path_prefix}' as {n} {cat} repo(s)")

    work, personal = votes["Work"], votes["Personal"]
    if work and personal:
        return Guess(None, "low", ["signals point both ways — asking directly"])
    if work == 0 and personal == 0:
        return Guess(None, "low", ["no matching categorized repos — asking directly"])
    cat = "Work" if work > personal else "Personal"
    confidence = "high" if (len(axes[cat]) >= 2 and votes[cat] >= 2) else "medium"
    return Guess(cat, confidence, reasons)
