from __future__ import annotations
import subprocess
from pathlib import Path

def git_available() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False

def _run(path: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True)

def is_git_repo(path: Path) -> bool:
    return _run(Path(path), "rev-parse", "--is-inside-work-tree").returncode == 0

def remotes(path: Path) -> dict[str, str]:
    out = _run(Path(path), "remote", "-v").stdout
    result = {}
    for line in out.splitlines():
        if "(fetch)" in line:
            name, url = line.split("\t")[0], line.split("\t")[1].split(" ")[0]
            result[name] = url
    return result

def list_git_repos(roots) -> list[tuple[str, Path]]:
    """Immediate subdirectories of each root that are git repos: (name, path)."""
    found: list[tuple[str, Path]] = []
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and is_git_repo(child):
                found.append((child.name, child))
    return found

def owner_commit_dates(path, identities, since=None, until=None, with_subjects=False):
    """Author-dates (YYYY-MM-DD) of commits authored by the owner, optionally within
    [since, until] inclusive. with_subjects=True -> {date: [subject, ...]} else a set."""
    owners = {o.lower() for o in identities}
    out = _run(Path(path), "log", "--date=short", "--pretty=%ad%x09%ae%x09%an%x09%s").stdout
    dates_with: dict[str, list[str]] = {}
    dates: set[str] = set()
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 3:
            continue
        date, email, name = parts[0], parts[1], parts[2]
        subject = parts[3] if len(parts) > 3 else ""
        if since and date < since:
            continue
        if until and date > until:
            continue
        hay = (email + " " + name).lower()
        if not any(o in hay for o in owners):
            continue
        if with_subjects:
            dates_with.setdefault(date, []).append(subject)
        else:
            dates.add(date)
    return dates_with if with_subjects else dates

def author_email_domains(path: Path) -> dict[str, int]:
    """Map of lowercased author-email domain -> commit count across history."""
    out = _run(Path(path), "log", "--pretty=%ae").stdout
    counts: dict[str, int] = {}
    for line in out.splitlines():
        line = line.strip()
        if "@" in line:
            dom = line.rsplit("@", 1)[1].lower()
            if dom:
                counts[dom] = counts.get(dom, 0) + 1
    return counts

def sync(journal_path: Path, message: str) -> str:
    if not git_available():
        return "git unavailable — local journal saved; not pushed"
    repo = Path(journal_path).parent
    if not is_git_repo(repo):
        return "not a git repo — local journal saved; not pushed"
    rel = Path(journal_path).name
    _run(repo, "add", rel)
    status = _run(repo, "status", "--porcelain", rel).stdout.strip()
    if status:
        _run(repo, "commit", "-m", message, rel)
    if "origin" not in remotes(repo):
        return "no 'origin' remote — committed locally; not pushed"
    push = _run(repo, "push", "origin", "HEAD")
    if push.returncode != 0:
        return f"push failed: {push.stderr.strip()[:120]}"
    return "pushed to origin"
