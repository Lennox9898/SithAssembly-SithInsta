# Local Command Console

The printable English reference is `Network-Intelligence-Command-Reference.pdf`. `Signal Desk` implements only the local, allowlisted commands below against its SQLite case database.

## Available commands

- `/help [topic]`
- `/context`
- `/find posts --query <text> [--min-risk 45] [--limit 50]`
- `/find accounts --query <text>`
- `/find mentions @handle`
- `/find links [--domain example.org]`
- `/source add <URL> [--label "Title"]`
- `/profile show|history|connections @handle`
- `/profile activity|aliases @handle`
- `/profile compare @account_a @account_b`
- `/graph build|centrality|communities`
- `/graph common @account_a @account_b`
- `/graph path @account_a @account_b [--max-hops 4]`
- `/timeline build`
- `/timeline compare @account_a @account_b`
- `/case create "Title" [--description "Text"]`
- `/case status`
- `/case note "Text"`
- `/case tag "Label"`
- `/review queue`
- `/review approve|reject claim:<id>`
- `/confidence set relationship:<id> <0-1>`
- `/contradictions`, `/duplicates [--type profile|source]`, `/gaps`
- `/agent status` or `/queue`
- `/history`
- `/report generate --format pdf`
- `/export case --format json|pdf`

Use `--case <id>` with a supported command to target a different local case. Each execution returns the normalized command, structured local data, evidence links, confidence where available, and suggested next commands.

## Current local command set

The current local executor implements only the commands listed above. Other catalog entries currently return `not_available`; they can be added later through explicit, tested adapters and command handlers.
