from __future__ import annotations
from pathlib import Path
from filelock import FileLock

from server.config import Config
from server.privacy import scan
from server.vocab import load_vocab, add_local_tag, TAGGING_GUIDANCE
from server import journal as J
from server.timeline import build_timeline, firsts
from server.ownership import resolve_repo_path, is_collaboration
from server import gitops


class JournalService:
    def __init__(self, config: Config, *, seed_vocab: Path, local_vocab: Path, rules_path: Path):
        self.cfg = config
        self.seed_vocab = Path(seed_vocab)
        self.local_vocab = Path(local_vocab)
        self.rules_path = Path(rules_path)
        self.lock = FileLock(str(self.cfg.journal_path) + ".lock")

    def _vocab(self):
        return load_vocab(self.seed_vocab, self.local_vocab)

    def _load_journal(self) -> J.Journal:
        if self.cfg.journal_path.exists():
            return J.parse(self.cfg.journal_path.read_text())
        return J.parse(J.new_journal_text())

    def _scan_all(self, *texts) -> list:
        findings = []
        for t in texts:
            if isinstance(t, list):
                for x in t:
                    findings += scan(x, self.cfg.owner_identities, self.cfg.dev_domains)
            elif t:
                findings += scan(t, self.cfg.owner_identities, self.cfg.dev_domains)
        return findings

    def log_decision(self, *, repo, title, session_focus, human_decisions, ai_execution,
                     source, domains, activities, tools=None, notable_artifacts=None,
                     category=None) -> dict:
        tools = tools or []
        vocab = self._vocab()
        unknown = vocab.validate(domains, activities)
        if unknown:
            return {"status": "bad_tags",
                    "message": f"unknown tags: {', '.join(unknown)}. Use list_tags or propose_tag."}
        findings = self._scan_all(title, session_focus, human_decisions, ai_execution,
                                  notable_artifacts, source, tools)
        if findings:
            spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
            return {"status": "blocked",
                    "message": f"write blocked (customer data): {spans}. Sanitize and retry."}
        with self.lock:
            jr = self._load_journal()
            known = jr.repo_category.get(repo)
            if known is None:
                if category is None:
                    return {"status": "needs_category",
                            "message": f"New repo '{repo}'. Is it Work or Personal? Re-call with category."}
                cat = "Work" if category.lower() == "work" else "Personal"
                jr.repo_category[repo] = cat
                jr.repo_order.setdefault(cat, [])
                if repo not in jr.repo_order[cat]:
                    jr.repo_order[cat].append(repo)
            else:
                cat = known
            acts = list(activities)
            rp = resolve_repo_path(repo, self.cfg.repo_roots)
            if rp and is_collaboration(rp, self.cfg.owner_identities) and "collaboration" not in acts:
                acts.append("collaboration")
            before = {(a, v) for _, a, v, _ in firsts(jr.entries)}
            import datetime
            date = datetime.date.today().isoformat()
            entry = J.Entry(date=date, title=title, repo=repo, category=cat,
                            domains=list(domains), activities=acts, tools=list(tools))
            entry.raw = _render_full_entry(entry, session_focus, human_decisions,
                                           ai_execution, notable_artifacts, source)
            jr.entries.append(entry)
            after = {(a, v) for _, a, v, _ in firsts(jr.entries)}
            new_firsts = sorted(v for (a, v) in (after - before))
            J.write_atomic(self.cfg.journal_path, J.render(jr, vocab))
        msg = f"journal updated: {repo} — {title}"
        if new_firsts:
            msg += " + first: " + ", ".join(new_firsts)
        return {"status": "logged", "message": msg, "firsts": new_firsts}

    def sync_journal(self) -> dict:
        with self.lock:
            jr = self._load_journal()
            n = len(jr.entries)
        out = gitops.sync(self.cfg.journal_path, "journal: sync")
        return {"status": "synced", "message": f"journal pushed: {n} entries ({out})"}

    def get_latest_entry(self, repo: str) -> dict:
        jr = self._load_journal()
        rel = [e for e in jr.entries if e.repo == repo]
        if not rel:
            uncategorized = repo not in jr.repo_category
            return {"status": "empty", "repo": repo, "uncategorized": uncategorized,
                    "message": "no entries yet"}
        last = sorted(rel, key=lambda e: e.date)[-1]
        return {"status": "ok", "entry": last.raw}

    def list_sections(self) -> dict:
        jr = self._load_journal()
        return {"Work": jr.repo_order.get("Work", []),
                "Personal": jr.repo_order.get("Personal", [])}

    def list_tags(self) -> dict:
        v = self._vocab()
        return {"domains": v.domains, "activities": v.activities, "guidance": TAGGING_GUIDANCE}

    def get_timeline(self) -> dict:
        jr = self._load_journal()
        return {"timeline": build_timeline(jr.entries)}

    def propose_tag(self, axis: str, name: str, gloss: str) -> dict:
        if axis not in ("domain", "activity"):
            return {"status": "error", "message": "axis must be 'domain' or 'activity'"}
        add_local_tag(self.local_vocab, axis, name, gloss)
        return {"status": "added", "message": f"added {axis}:{name}; first use will record a Timeline first"}

    def preflight(self) -> dict:
        report = {}
        report["git"] = gitops.git_available()
        report["journal_writable"] = self.cfg.journal_path.parent.exists() or True
        repo_dir = self.cfg.journal_path.parent
        report["journal_is_git_repo"] = gitops.is_git_repo(repo_dir)
        report["remotes"] = gitops.remotes(repo_dir) if report["journal_is_git_repo"] else {}
        report["repo_roots_exist"] = {str(r): Path(r).expanduser().exists() for r in self.cfg.repo_roots}
        return {"status": "ok", "report": report}


def _render_full_entry(e, session_focus, human_decisions, ai_execution, notable_artifacts, source) -> str:
    tags = f"domain: {', '.join(e.domains)} · activity: {', '.join(e.activities)}"
    if e.tools:
        tags += f" · tools: {', '.join(e.tools)}"
    lines = [
        f"### {e.date} — {e.title}", "",
        f"**Session focus:** {session_focus}", "",
        "**Human-driven decisions:**",
        *[f"- {d}" for d in human_decisions], "",
        "**AI execution:**",
        *[f"- {a}" for a in ai_execution], "",
    ]
    if notable_artifacts:
        lines.append(f"**Notable artifacts:** {notable_artifacts}")
    lines.append(f"**Source:** {source}")
    lines += ["", f"**Tags:** {tags}"]
    return "\n".join(lines).rstrip() + "\n"
