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
3. **Verify your environment:** Call the `preflight` tool from your client to confirm git, remotes, and repo roots are all healthy.
4. **Install the git hooks** (privacy backstop): in `.git/config` under `[core]`, set `hooksPath = .githooks`.

## Greenfield deployment (starting fresh, no existing journal)

If you do **not** already have a journal, this is the whole flow:

1. **Get your own private copy of this engine.** Create a new **private** repo from it (e.g. on GitHub), or clone this one and point `origin` at your private remote. The journal will live and sync there.
2. **Install + configure** (see Setup above). In `config.toml`, set `owner_identities` to include your email(s), git name, **and your git-host username** (needed so collaboration-detection knows which repos are yours), and set `repo_roots` to the directories your projects live under.
3. **Register the MCP server** in your AI tool(s) (see below).
4. **Install the hooks:** in `.git/config` under `[core]`, set `hooksPath = .githooks`.
5. **Run `preflight`** from your client to confirm git, `origin`, and repo roots are healthy.
6. **Start logging.** You do **not** create the journal file by hand — the first `log_decision` creates `DECISIONS_JOURNAL.md` automatically from the built-in template (intro header, TOC, Timeline, then your entry). On your first new repo it will ask whether the repo is Work or Personal.
7. **Sync when you push.** `sync_journal` commits the pending entries and pushes them to your private `origin`.

> Already have an existing journal to import? That's a migration, not a greenfield start — it needs a one-time move/classify/privacy-audit/backfill pass (separate process), not these steps.

## Register the MCP server

**Claude Desktop / Claude Code** (`claude_desktop_config.json` or `.mcp.json`) — point `command` at your venv's **python binary** and launch the module with `-m server.main`:

```json
{
  "mcpServers": {
    "decision-journal": {
      "command": "/absolute/path/to/human-decision-journal/.venv/bin/python",
      "args": ["-m", "server.main"],
      "cwd": "/absolute/path/to/human-decision-journal"
    }
  }
}
```

**Cursor / Zed / OpenCode:** add the same `command`/`args`/`cwd` under each tool's MCP config section.

> **macOS gotcha — invoke `python`, not the console-script wrapper.** `pip install -e .` also generates a wrapper at `.venv/bin/human-decision-journal`. It works from a terminal, but GUI-launched clients (Claude Desktop, Cursor) spawn it in a context where the re-exec'd interpreter is denied its own `.venv/pyvenv.cfg` — the server dies instantly with `PermissionError: [Errno 1] Operation not permitted: .../pyvenv.cfg` and the client reports "Server disconnected." Pointing `command` straight at `.venv/bin/python` with `args: ["-m", "server.main"]` avoids it. (Terminal-based clients like Claude Code can use either form.)

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

The journal records decisions and reasoning only. The guard hard-blocks emails (non-owner), non-dev-domain URLs, IPs, ticket IDs, phone numbers, payment cards, SSNs, and common secret formats — at the MCP write boundary and again in the pre-commit hook. Customer/person/company **names** in prose cannot be reliably pattern-detected; keep them out by habit. Note: a bare four-part dotted number (e.g. a build version like `1.2.3` followed by a fourth segment) can be read as an IPv4 address and blocked — rephrase (e.g. "v1.2.3 build 4") if that happens.

## License

MIT (or your choice).
