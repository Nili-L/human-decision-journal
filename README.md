# human-decision-journal

An MCP server that maintains a private **Decisions Journal** — a record of *what you decided and why* while building software — across whatever AI tool you use (Claude Code, Claude Desktop, Cursor, Zed, OpenCode, …). It tags every entry by **domain** and **activity**, keeps a **Timeline of firsts**, and **hard-blocks customer data** before anything is written.

## Setup

1. **Install** (Python 3.11+):
   ```bash
   pip install -e .
   ```
2. **Configure:**
   ```bash
   cp config.example.toml config.toml
   # edit owner_name, owner_identities, journal_path, repo_roots, dev_domains
   ```
3. **Verify your environment:**
   ```bash
   python -c "from server.main import build_server; print(build_server().name)"
   ```
   Then call the `preflight` tool from your client to confirm git, remotes, and repo roots.
4. **Install the git hooks** (privacy backstop):
   ```bash
   git config core.hooksPath .githooks
   ```

## Register the MCP server

**Claude Desktop / Claude Code** (`claude_desktop_config.json` or `.mcp.json`):
```json
{
  "mcpServers": {
    "decision-journal": {
      "command": "python",
      "args": ["-m", "server.main"],
      "cwd": "/absolute/path/to/human-decision-journal"
    }
  }
}
```

**Cursor / Zed / OpenCode:** add the same `command`/`args`/`cwd` under each tool's MCP config section.

## Optional: proactive journaling

To have agents journal automatically at commit/push, add this short block to your project's `AGENTS.md`:

```markdown
## Decisions Journal
Maintain the owner's Decisions Journal via the `decision-journal` MCP. On commit, call `log_decision`
(read `get_latest_entry` first; tag with `list_tags`). On push, call `sync_journal`. The MCP carries the full rules.
```

(That's it — no need to overwrite any existing rules; this is purely additive.)

## How it works

- **commit** in your work repo → `log_decision` writes the entry locally.
- **push** in your work repo → `sync_journal` commits and pushes the journal to its private remote.
- Entries are tagged on two axes; the server records the **first** time you work in a new area or use a new tool.
- The privacy guard runs server-side on every write *and* in the pre-commit hook.

## Tools

| Tool | Purpose |
|---|---|
| `log_decision` | Log a decision locally (commit-trigger); structured fields + two-axis tags. |
| `sync_journal` | Commit + push the journal to `origin` (push-trigger). |
| `get_latest_entry` | Most recent entry for a repo (read before logging). |
| `list_sections` | Existing repos grouped by Work/Personal. |
| `list_tags` | The domain + activity vocabularies with glosses. |
| `get_timeline` | Firsts ledger + "what I do most" rollup. |
| `propose_tag` | Add a new tag (owner confirms). |
| `preflight` | Environment/health check. |

## Privacy

The journal records decisions and reasoning only. The guard hard-blocks emails (non-owner), non-dev-domain URLs, IPs, ticket IDs, phone numbers, payment cards, SSNs, and common secret formats — at the MCP write boundary and again in the pre-commit hook. Customer/person/company **names** in prose cannot be reliably pattern-detected; keep them out by habit.

## License

MIT (or your choice).
