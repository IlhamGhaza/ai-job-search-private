#!/usr/bin/env bun
// upwork-search: Upwork jobs through the official GraphQL API (approved key
// required), else search-provider leads. Upwork's Terms forbid scraping, so
// https://www.upwork.com/ pages are never requested here.

import { runGigCli } from "./gig.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `upwork-search - Upwork gigs (official GraphQL API, else search-engine leads)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [flags]
  bun run src/cli.ts detail <id|job URL>     (API only; MANUAL_ONLY without a token)

SEARCH FLAGS
  --query, -q <text>     Upwork search expression. Default "flutter".
  --jobage <days>        Posted within N days.
  --page <n> / --limit, -n <n> (max 50 via API, 20 via search engine) / --format json|table|plain

SETUP
  UPWORK_ACCESS_TOKEN     OAuth 2.0 access token for an approved Upwork API key
                          (scopes: Common Entities read-only, Read marketplace Job Postings).
  BRAVE_SEARCH_API_TOKEN  fallback discovery when UPWORK_ACCESS_TOKEN is unset.
Never scrape upwork.com: the Terms forbid it and accounts get banned.
`

await runGigCli({ name: "upwork-search", help: HELP, search: runSearch, detail: runDetail })
