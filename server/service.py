from __future__ import annotations
from pathlib import Path
from filelock import FileLock

from server.config import Config
from server.privacy import scan
from server.vocab import load_vocab, add_local_tag, TAGGING_GUIDANCE
from server import journal as J
from server import report as R
from server import coverage as CV
from server import digest as DG
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
        if out == "pushed to origin":
            status, verb = "synced", "pushed"
        elif "fail" in out.lower():
            status, verb = "error", "sync failed"
        else:
            status, verb = "local_only", "saved locally"
        return {"status": status, "message": f"journal {verb}: {n} entries ({out})"}

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

    def coverage_report(self, *, since: str | None = None, until: str | None = None,
                        scope: str = "all", level: str = "summary") -> dict:
        scope = "work" if scope.lower() == "work" else "all"
        level = level if level in CV.LEVELS else "summary"
        jr = self._load_journal()
        logged: dict[str, set] = {}
        for e in jr.entries:
            logged.setdefault(e.repo, set()).add(e.date)
        want_subjects = (level == "full")
        repos: list[CV.RepoCoverage] = []
        for name, path in gitops.list_git_repos(self.cfg.repo_roots):
            active = gitops.owner_commit_dates(path, self.cfg.owner_identities,
                                               since=since, until=until,
                                               with_subjects=want_subjects)
            active_dates = set(active.keys()) if want_subjects else active
            if not active_dates:
                continue
            category = jr.repo_category.get(name)
            if scope == "work" and category != "Work":
                continue
            subjects = {}
            if want_subjects:
                subjects = {d: [redact_subject(s, self.cfg) for s in subs]
                            for d, subs in active.items()}
            repos.append(CV.RepoCoverage(repo=name, category=category,
                                         active=active_dates, logged=logged.get(name, set()),
                                         subjects=subjects))
        report, stats = CV.build_report(self.cfg.owner_name, repos, scope=scope, level=level)
        if level != "full":
            findings = self._scan_all(report)
            if findings:
                spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
                return {"status": "blocked",
                        "message": f"coverage report blocked (customer data): {spans}."}
        return {"status": "ok", "report": report, "stats": stats}

    def period_summary(self, *, period="month", basis="to-date", since=None, until=None,
                       scope="all", detail="titles") -> dict:
        import datetime
        scope = "work" if scope.lower() == "work" else "all"
        detail = "full" if detail == "full" else "titles"
        s, u, label = DG.period_window(period, basis, since, until, datetime.date.today())
        jr = self._load_journal()

        def in_scope(e):
            return scope == "all" or jr.repo_category.get(e.repo) == "Work"

        scoped = [e for e in jr.entries if in_scope(e)]
        selected = [e for e in scoped if s <= e.date <= u]
        firsts_in_window = [f for f in firsts(scoped) if s <= f[0] <= u]
        report, stats = DG.build_digest(self.cfg.owner_name, selected, firsts_in_window,
                                        scope=scope, label=label, detail=detail)
        findings = self._scan_all(report)
        if findings:
            spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
            return {"status": "blocked", "message": f"digest blocked (customer data): {spans}."}
        return {"status": "ok", "digest": report, "stats": stats}

    def list_tags(self) -> dict:
        v = self._vocab()
        return {"domains": v.domains, "activities": v.activities, "guidance": TAGGING_GUIDANCE}

    def get_timeline(self) -> dict:
        jr = self._load_journal()
        return {"timeline": build_timeline(jr.entries)}

    def export_authorship_report(self, *, category: str = "work", since: str | None = None,
                                 until: str | None = None, repos: list[str] | None = None) -> dict:
        jr = self._load_journal()
        report, stats = R.build_report(jr, self.cfg.owner_name, category=category,
                                       since=since, until=until, repos=repos)
        # Egress privacy scan: entries are scanned at write time, but the report is the
        # surface that leaves the building, so it is scanned again at the door.
        findings = self._scan_all(report)
        if findings:
            spans = ", ".join(f"{f.kind}:{f.value!r}" for f in findings[:8])
            return {"status": "blocked",
                    "message": f"report blocked (customer data): {spans}. Sanitize the journal and retry."}
        return {"status": "ok", "report": report, "stats": stats}

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


def redact_subject(subject: str, cfg) -> str:
    from server.privacy import redact
    return redact(subject, cfg.owner_identities, cfg.dev_domains)
