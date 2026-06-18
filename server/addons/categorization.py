from __future__ import annotations
import json
from pathlib import Path

from server.categorize import signals_for, guess, Signals
from server.ownership import resolve_repo_path

_RULES = Path(__file__).with_name("categorization.RULES.md")


def rules_snippet() -> str:
    return _RULES.read_text() if _RULES.exists() else ""


def _labeled_signals(svc) -> list[tuple[Signals, str]]:
    jr = svc._load_journal()
    out: list[tuple[Signals, str]] = []
    for repo, cat in jr.repo_category.items():
        path = resolve_repo_path(repo, svc.cfg.repo_roots)
        if path is None:
            continue
        try:
            out.append((signals_for(path, svc.cfg.owner_identities), cat))
        except Exception:
            continue
    return out


def _write_cache(cfg, labeled, target_repo, result) -> None:
    if cfg.state_dir is None:
        return
    sd = Path(cfg.state_dir)
    try:
        sd.mkdir(parents=True, exist_ok=True)
        data = {
            "labeled": [
                {"remote_org": s.remote_org, "email_domains": list(s.email_domains),
                 "path_prefix": s.path_prefix, "is_collaboration": s.is_collaboration,
                 "category": c}
                for s, c in labeled
            ],
            "last_guess": {"repo": target_repo, "guess": result.guess,
                           "confidence": result.confidence, "reasons": result.reasons},
        }
        (sd / "categories.local.json").write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def categorize_repo(svc, repo: str) -> dict:
    path = resolve_repo_path(repo, svc.cfg.repo_roots)
    if path is None:
        return {"status": "no_path", "guess": None, "confidence": "low",
                "reasons": [f"repo '{repo}' not found under repo_roots — ask Work or Personal directly"]}
    labeled = _labeled_signals(svc)
    target = signals_for(path, svc.cfg.owner_identities)
    result = guess(target, labeled)
    _write_cache(svc.cfg, labeled, repo, result)
    return {"status": "ok", "guess": result.guess,
            "confidence": result.confidence, "reasons": result.reasons}


def register(mcp, svc, cfg) -> None:
    @mcp.tool(description=(
        "Categorization add-on: guess whether a repo is Work or Personal from signals "
        "(git-host org, author email domain, folder) learned off already-categorized repos. "
        "Returns {guess, confidence, reasons}; guess may be null when uncertain. ALWAYS confirm "
        "with the owner before logging — never auto-file. Call on a needs_category response."))
    def guess_category(repo: str) -> dict:
        return categorize_repo(svc, repo)
