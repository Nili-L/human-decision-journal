from __future__ import annotations
import subprocess
from pathlib import Path


def resolve_repo_path(repo: str, repo_roots: list[Path]) -> Path | None:
    for root in repo_roots:
        candidate = Path(root).expanduser() / repo
        if candidate.is_dir():
            return candidate
    return None


def _git_out(path: Path, *args) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except FileNotFoundError:
        return ""


def is_collaboration(repo_path: Path, owner_identities: list[str]) -> bool:
    """True when the repo's canonical ownership is NOT the owner's:
    an origin/upstream URL owner that isn't the owner, or authorship majority not-owner."""
    owners = {o.lower() for o in owner_identities}
    for remote in ("upstream", "origin"):
        url = _git_out(repo_path, "remote", "get-url", remote)
        if not url:
            continue
        tail = url.split(":")[-1] if ":" in url and "//" not in url else url.split("//")[-1]
        parts = [p for p in tail.replace(":", "/").split("/") if p]
        owner_seg = parts[-2].lower() if len(parts) >= 2 else ""
        if owner_seg:
            return owner_seg not in owners
    log = _git_out(repo_path, "shortlog", "-sne", "HEAD")
    if not log:
        return False
    mine = others = 0
    for line in log.splitlines():
        count_str = line.strip().split("\t")[0]
        try:
            n = int(count_str)
        except ValueError:
            continue
        low = line.lower()
        if any(o in low for o in owners):
            mine += n
        else:
            others += n
    return others > mine
