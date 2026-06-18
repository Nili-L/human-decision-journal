from __future__ import annotations
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from server.config import load_config
from server.service import JournalService

ROOT = Path(__file__).resolve().parents[1]


def _instructions(rules_path: Path, cfg) -> str:
    rules = rules_path.read_text() if rules_path.exists() else ""
    return f"Journal owner: {cfg.owner_name}.\n\n{rules}"


def build_server(config_path: Path = ROOT / "config.toml") -> FastMCP:
    cfg = load_config(config_path)
    svc = JournalService(cfg, seed_vocab=ROOT / "work-vocab.toml",
                         local_vocab=ROOT / "work-vocab.local.toml",
                         rules_path=ROOT / "RULES.md")
    cat_addon = None
    if cfg.categorization_enabled:
        from server.addons import categorization as cat_addon

    instructions = _instructions(ROOT / "RULES.md", cfg)
    if cat_addon:
        snippet = cat_addon.rules_snippet()
        if snippet:
            instructions = instructions + "\n\n" + snippet

    mcp = FastMCP("decision-journal", instructions=instructions)

    @mcp.tool(description=(
        "Log one substantive decision to the journal (commit-trigger action; local write only). "
        "Tag the OWNER's contribution with domains[] and activities[] from list_tags (>=1 each; "
        "fewest true tags; never invent synonyms — use propose_tag). Do NOT pass 'collaboration' "
        "(server applies it). The server hard-blocks customer data — sanitize and retry on a block. "
        "Read get_latest_entry(repo) first and extend rather than duplicate. "
        "On a new repo, pass category='work'|'personal'."))
    def log_decision(repo: str, title: str, session_focus: str, human_decisions: list[str],
                     ai_execution: list[str], source: str, domains: list[str],
                     activities: list[str], tools: list[str] | None = None,
                     notable_artifacts: str | None = None, category: str | None = None) -> dict:
        return svc.log_decision(repo=repo, title=title, session_focus=session_focus,
                                human_decisions=human_decisions, ai_execution=ai_execution,
                                source=source, domains=domains, activities=activities,
                                tools=tools, notable_artifacts=notable_artifacts, category=category)

    @mcp.tool(description="Push-trigger action: commit pending journal entries and push to origin. Requires git.")
    def sync_journal() -> dict:
        return svc.sync_journal()

    @mcp.tool(description="Most recent entry for a repo, so you can extend or skip rather than duplicate.")
    def get_latest_entry(repo: str) -> dict:
        return svc.get_latest_entry(repo)

    @mcp.tool(description="Existing repo sections grouped by Work/Personal category.")
    def list_sections() -> dict:
        return svc.list_sections()

    @mcp.tool(description="The two controlled tag vocabularies (domain + activity) with glosses and usage guidance.")
    def list_tags() -> dict:
        return svc.list_tags()

    @mcp.tool(description="The Timeline: firsts ledger + 'what I do most' rollup.")
    def get_timeline() -> dict:
        return svc.get_timeline()

    @mcp.tool(description=(
        "Export a shareable Authorship Report from the journal — a work-scoped, read-only "
        "evidentiary view of what the owner decided vs. what the agent did, for a manager or "
        "client. Defaults to Work entries only (Personal is excluded). Optionally narrow by "
        "since/until ('YYYY-MM-DD', inclusive) and repos[]. Never writes the journal or touches "
        "git; re-runs the customer-data hard-block over the rendered report before returning."))
    def export_authorship_report(category: str = "work", since: str | None = None,
                                 until: str | None = None, repos: list[str] | None = None) -> dict:
        return svc.export_authorship_report(category=category, since=since, until=until, repos=repos)

    @mcp.tool(description=(
        "Read-only coverage report: reconcile your own git commits against logged journal "
        "entries, by active day. Private by default. level='headline'|'summary'|'detailed'|"
        "'full' (increasing disclosure); scope='all' (incl. personal) or 'work'. Optional "
        "since/until ('YYYY-MM-DD', inclusive). Commit subjects appear only at 'full' and are "
        "redacted for customer data."))
    def coverage_report(since: str | None = None, until: str | None = None,
                        scope: str = "all", level: str = "summary") -> dict:
        return svc.coverage_report(since=since, until=until, scope=scope, level=level)

    @mcp.tool(description=(
        "Read-only period digest: roll a time window of journal entries into a summary "
        "(decisions, projects, top tags, new 'firsts'). period='week'|'month'|'quarter'; "
        "basis='rolling'(fixed 7/30/90d)|'calendar'(exact 1wk/1mo/3mo)|'to-date'|'previous'; "
        "since/until ('YYYY-MM-DD') override. scope='all'|'work'. detail='titles'|'full' "
        "(full includes each entry's Human-driven decision bullets)."))
    def period_summary(period: str = "month", basis: str = "to-date",
                       since: str | None = None, until: str | None = None,
                       scope: str = "all", detail: str = "titles") -> dict:
        return svc.period_summary(period=period, basis=basis, since=since, until=until,
                                  scope=scope, detail=detail)

    @mcp.tool(description="Propose a new tag (axis='domain'|'activity'); owner confirms by approving the call.")
    def propose_tag(axis: str, name: str, gloss: str) -> dict:
        return svc.propose_tag(axis, name, gloss)

    @mcp.tool(description="First-run environment check: git, journal repo remotes/hooks, repo roots.")
    def preflight() -> dict:
        return svc.preflight()

    @mcp.resource("file://rules")
    def rules() -> str:
        return (ROOT / "RULES.md").read_text()

    @mcp.prompt()
    def journaling_rules() -> str:
        return (ROOT / "RULES.md").read_text()

    if cat_addon:
        cat_addon.register(mcp, svc, cfg)

    return mcp


def main():
    build_server().run()


if __name__ == "__main__":
    main()
