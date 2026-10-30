---
name: workana-search
version: 1.0.0
description: >
  Use this skill to discover Workana freelance gigs (Flutter / mobile) for the
  /gigs workflow - search-engine leads only, never a crawl of Workana. Trigger
  phrases: Workana gigs, Workana freelance Flutter projects.
context: fork
category: freelance  # /gigs runs this skill; /scrape skips freelance skills
enabled: true  # set to false to keep this platform installed but have /gigs skip it
allowed-tools: Bash(bun run .agents/skills/workana-search/cli/src/cli.ts *)
---

# Workana Gig Discovery Skill

Workana: Latin-America-focused marketplace (Spanish/Portuguese; some English projects).

**Access route: search-provider discovery.** One `site:workana.com/job` query
per host on the **Brave Search API**. Workana itself is never requested, so
its terms on automated access and its robots.txt are not engaged. `detail`
always returns `MANUAL_ONLY`: open the link, read the gig, and paste its text
into `/propose`.

No public API (checked 2026-10-30). Many projects are written in Spanish or Portuguese; the language gate in 04-job-evaluation.md still applies (Indonesian and English only in the profile).

## Setup

`BRAVE_SEARCH_API_TOKEN` (see `linkedin-posts-search` SKILL.md for cost and
quota). Missing token -> `MISSING_CREDENTIALS`, which `/gigs` reports as
`skipped (no credentials)`.

## Commands

```bash
bun run .agents/skills/workana-search/cli/src/cli.ts search [-q "flutter firebase"] [--jobage 7] [--limit 20] [--format json|table|plain]
bun run .agents/skills/workana-search/cli/src/cli.ts detail <url>      # MANUAL_ONLY
bun run .agents/skills/workana-search/cli/src/cli.ts --help
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

Offline tests: `cd .agents/skills/workana-search/cli && bun install && bun run typecheck && bun test`.
