---
name: contra-search
version: 1.0.0
description: >
  Use this skill to discover Contra freelance gigs (Flutter / mobile) for the
  /gigs workflow - search-engine leads only, never a crawl of Contra. Trigger
  phrases: Contra gigs, Contra freelance Flutter projects.
context: fork
category: freelance  # /gigs runs this skill; /scrape skips freelance skills
enabled: true  # set to false to keep this platform installed but have /gigs skip it
allowed-tools: Bash(bun run .agents/skills/contra-search/cli/src/cli.ts *)
---

# Contra Gig Discovery Skill

Contra: commission-free freelance network; opportunities are posted by clients and freelancers apply with a profile.

**Access route: search-provider discovery.** One `site:contra.com/opportunity` query
per host on the **Brave Search API**. Contra itself is never requested, so
its terms on automated access and its robots.txt are not engaged. `detail`
always returns `MANUAL_ONLY`: open the link, read the gig, and paste its text
into `/propose`.

No public API for opportunities (checked 2026-10-30). Contra is open worldwide; payouts go through Contra (Stripe/PayPal) - confirm Indonesia payouts in your account settings.

## Setup

`BRAVE_SEARCH_API_TOKEN` (see `linkedin-posts-search` SKILL.md for cost and
quota). Missing token -> `MISSING_CREDENTIALS`, which `/gigs` reports as
`skipped (no credentials)`.

## Commands

```bash
bun run .agents/skills/contra-search/cli/src/cli.ts search [-q "flutter firebase"] [--jobage 7] [--limit 20] [--format json|table|plain]
bun run .agents/skills/contra-search/cli/src/cli.ts detail <url>      # MANUAL_ONLY
bun run .agents/skills/contra-search/cli/src/cli.ts --help
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

Offline tests: `cd .agents/skills/contra-search/cli && bun install && bun run typecheck && bun test`.
