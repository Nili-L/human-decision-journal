from pathlib import Path
from server.main import build_server


def _tool_names(mcp) -> set[str]:
    # _tool_manager.list_tools() is synchronous and returns list[Tool] objects.
    # Each Tool has a .name attribute (keyed in _tool_manager._tools dict).
    tools = mcp._tool_manager.list_tools()
    return {t.name for t in tools}


def test_build_server_registers_tools(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        f'journal_path="{tmp_path/"DECISIONS_JOURNAL.md"}"\n'
        'repo_roots=[]\ndev_domains=["github.com"]\n'
    )
    mcp = build_server(config_path=cfg)
    names = _tool_names(mcp)
    assert {"log_decision", "sync_journal", "get_latest_entry",
            "list_sections", "list_tags", "get_timeline", "propose_tag", "preflight"} <= names


def test_coverage_tool_registered(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'owner_name="Jo"\nowner_identities=["jo@x.com"]\n'
        f'journal_path="{tmp_path/"DECISIONS_JOURNAL.md"}"\n'
        'repo_roots=[]\ndev_domains=["github.com"]\n'
    )
    mcp = build_server(config_path=cfg)
    assert "coverage_report" in _tool_names(mcp)
