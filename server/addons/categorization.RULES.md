## Categorization add-on (Work/Personal)

When `log_decision` returns `needs_category` for a repo, do NOT ask blind first — call
`guess_category(repo)`.

- If it returns a `guess` ("Work"/"Personal"), tell the owner what it looks like and why,
  and confirm: e.g. *"This repo looks like **Work** — <reasons>. Right?"* Then re-call
  `log_decision` with the confirmed `category`. Never auto-file; always let the owner override.
- If `guess` is null (low confidence / not enough history / conflicting signals), ask
  plainly: *"Is this repo Work or Personal?"*
