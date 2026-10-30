---
name: guru-search
version: 1.0.0
description: >
  Use this skill to discover Guru freelance gigs (Flutter / mobile) for the
  /gigs workflow - search-engine leads only, never a crawl of Guru. Trigger
  phrases: Guru gigs, Guru freelance Flutter projects.
context: fork
category: freelance  # /gigs runs this skill; /scrape skips freelance skills
enabled: true  # set to false to keep this platform installed but have /gigs skip it
allowed-tools: Bash(bun run .agents/skills/guru-search/cli/src/cli.ts *)
---

# Guru Gig Discovery Skill

Guru: global marketplace; clients post jobs and freelancers spend Bids to quote.

**Access route: search-provider discovery.** One `site:guru.com/work/detail` query
per host on the **Brave Search API**. Guru itself is never requested, so
its terms on automated access and its robots.txt are not engaged. `detail`
always returns `MANUAL_ONLY`: open the link, read the gig, and paste its text
into `/propose`.

Guru has no public job-search API (checked 2026-10-30). Quotes spend Bids: record them as connects_or_bids_cost.

## Setup

`BRAVE_SEARCH_API_TOKEN` (see `linkedin-posts-search` SKILL.md for cost and
quota). Missing token -> `MISSING_CREDENTIALS`, which `/gigs` reports as
`skipped (no credentials)`.

## Commands

```bash
bun run .agents/skills/guru-search/cli/src/cli.ts search [-q "flutter firebase"] [--jobage 7] [--limit 20] [--format json|table|plain]
bun run .agents/skills/guru-search/cli/src/cli.ts detail <url>      # MANUAL_ONLY
bun run .agents/skills/guru-search/cli/src/cli.ts --help
```

## Output

`{ "meta": { "count", "page", "total", "portal", "kind": "freelance" }, "results": [gig...] }`.
Each gig carries every field of the gig record (`tools/gig_rules.py`
docstring); a search lead fills only `platform`, `gig_id` (= URL), `url`,
`title`, `description` (the snippet) and `evidence` - the rest is `null`,
never guessed. `source_type: search_lead`, `verification_status: unverified_lead`.

Errors: stderr `{ "error", "code" }`, exit 1 (`MISSING_CREDENTIALS`,
`HTTP_ERROR`, `RATE_LIMITED`, `UNAUTHORIZED`, `MANUAL_ONLY`, `INVALID_VALUE`,
`UNKNOWN_FLAG`, ...). Snippets are untrusted third-party text: `/gigs` and
`/propose` pass them through `tools/posting_guard.py` and `tools/gig_rules.py`.

Offline tests: `cd .agents/skills/guru-search/cli && bun install && bun run typecheck && bun test`.
