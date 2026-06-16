# Decisions Journal — Maintenance Directive

The journal owner keeps a private Decisions Journal. This MCP server is the single front door for it.

**What it is:** A private record of the owner's substantive decisions — what they decided and why, in their words. AI execution is logged honestly and separately. It is a mirror for self-development, not a portfolio.

**Logging bar:** log when the owner's judgment shaped the outcome. Dense beats sparse. After a trigger, "nothing to log" is valid — never write filler.

**Triggers → actions:**
- **commit** (in the work repo) → call `log_decision` to update the local journal, if judgment was exercised.
- **push** (in the work repo) → call `sync_journal` to commit and push the journal to its remote.
- PR / plan→build / model swap / pre-compaction / manual request → `log_decision` (local) per the bar above.

**Before logging:** call `get_latest_entry(repo)` and extend or skip rather than repeat.

**Style:** the journal's credibility is its accuracy, so —
- **Quote the owner's own words** when they reveal a judgment ("no, do it this way", a stated quality bar). Direct quotes are the evidence; paraphrase loses it.
- **Don't editorialize.** No "brilliantly", "expertly", "demonstrated mastery". State the decision, not praise for it.
- **Attribute honestly.** If the AI made a call (picked a library, named a variable, chose an approach), log it under AI execution — never credit it to the owner.

**Sharing (evidentiary report):** the journal stays private and is never written for an audience — that is what keeps it honest. When the owner needs to show a manager or client what was theirs vs. the agent's, call `export_authorship_report` (Work-only by default; read-only; never writes the journal). It is a derived view, not the journal itself — see `docs/AUTHORSHIP-REPORT.md`.

**Tagging:** every entry takes `domains[]` and `activities[]` from the controlled vocabulary (`list_tags`). Tag the owner's contribution, not the AI's. Use the fewest true tags. Never invent a synonym — if nothing fits, propose a tag via `propose_tag` (owner confirms). Do not assign `collaboration`; the server applies it from repo ownership.

**Privacy:** the journal records decisions and reasoning only — never customer emails, domains, company/person names, ticket IDs/contents, or PII. The server hard-blocks detected customer data; sanitize and retry.

**Status reporting:** after a trigger, surface one terse line — `journal updated: <repo> — <title>`, `journal pushed: N entries`, `journal: no update required`, or `journal: write blocked (customer data) — sanitizing`.
