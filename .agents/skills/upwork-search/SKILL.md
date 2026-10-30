---
name: upwork-search
version: 1.0.0
description: >
  Use this skill to find Upwork gigs (Flutter / mobile) for the /gigs
  workflow - through Upwork's official GraphQL API when you hold an approved
  API key, else as search-engine leads. Never scrapes upwork.com. Trigger
  phrases: Upwork gigs, Upwork Flutter jobs, freelance Flutter on Upwork.
context: fork
category: freelance  # /gigs runs this skill; /scrape skips freelance skills
enabled: true  # set to false to keep this platform installed but have /gigs skip it
allowed-tools: Bash(bun run .agents/skills/upwork-search/cli/src/cli.ts *)
---

# Upwork Gig Search Skill

## ⚠️ Terms of use

Upwork's Terms of Use and API Terms forbid scraping, crawling or automating
the Upwork site, and an account ban is hard to undo. This skill therefore:

- reads gigs **only** through the official GraphQL API (`https://api.upwork.com/graphql`)
  with **your own approved key**, or, without a key, through the Brave Search API
  (`site:upwork.com/freelance-jobs/apply`). It never requests an upwork.com page;
- never submits proposals or spends Connects. `/propose` fills the proposal form
  in your own browser and **you** click Send (fill-only is enforced in
  `tools/freelance_guard.py`, not just a default).

## Setup

| Variable | What |
|----------|------|
| `UPWORK_ACCESS_TOKEN` | OAuth 2.0 access token for an approved Upwork API key |
| `BRAVE_SEARCH_API_TOKEN` | fallback discovery when no Upwork token is set |

**Applying for Upwork API access:** sign in at <https://www.upwork.com/developer/keys/apply>
(your account must be ID-verified). Request an OAuth 2.0 key with a short, honest
description ("personal tool to read job postings that match my skills; no
proposals are sent through the API"), callback URL `https://localhost`, and the
scopes **Common Entities - Read-Only Access** and **Read marketplace Job
Postings**. Approval is manual and can take days or be declined. After
approval, run the authorization-code flow once (Upwork developer docs,
"Authentication") to get an access token and export it. Tokens expire
(about 24 h); refresh with the refresh token. Keep both in your shell
environment or a gitignored `.env`, never in the repo.

Without either token the CLI exits `MISSING_CREDENTIALS`, which `/gigs`
reports as `skipped (no credentials)`.

## Commands

```bash
bun run .agents/skills/upwork-search/cli/src/cli.ts search -q "flutter" [--jobage 7] [--limit 25] [--format json|table|plain]
bun run .agents/skills/upwork-search/cli/src/cli.ts detail <numeric id|job URL with ~0<id>>   # API only; MANUAL_ONLY without a token
bun run .agents/skills/upwork-search/cli/src/cli.ts --help
```

## Output

`{ "meta": { ..., "kind": "freelance" }, "results": [gig...] }` - the gig record
documented in `tools/gig_rules.py`. API results carry client country, payment
verification, rating (`totalFeedback`), hires, total spent, budget, duration,
skills, proposal count and posting date when Upwork returns them; anything
missing is `null`. `connects_or_bids_cost` is always `null` (not in the public
schema): read the Connects on the proposal page before you approve spending.
Search-engine leads fill only title, URL and snippet.

The GraphQL field names follow Upwork's published schema, which Upwork
changes over time. A `BAD_RESPONSE` naming an unknown field means: introspect
the schema with your token and adjust `SEARCH_QUERY` / `parseNode` in
`cli/src/commands/search.ts`.

Errors: stderr `{ "error", "code" }`, exit 1 (`MISSING_CREDENTIALS`,
`UNAUTHORIZED` - expired token or missing scope, `RATE_LIMITED`, `HTTP_ERROR`,
`BAD_RESPONSE`, `MANUAL_ONLY`, ...). Gig text is untrusted third-party data.

Offline tests: `cd .agents/skills/upwork-search/cli && bun install && bun run typecheck && bun test`.
