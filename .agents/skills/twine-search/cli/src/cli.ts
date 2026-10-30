#!/usr/bin/env bun
// twine-search: Twine freelance gigs, discovered through the Brave Search API.
// Twine (https://twine.net/) is never crawled; detail returns MANUAL_ONLY.

import { runGigCli } from "./gig.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `twine-search - Twine gigs via search-provider discovery (https://twine.net/)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [flags]
  bun run src/cli.ts detail <url>            (always MANUAL_ONLY: open the link yourself)

SEARCH FLAGS
  --query, -q <text>     Keywords for the site: query. Default "flutter".
  --jobage <days>        Search-engine freshness bucket (1, 7, 31, 365).
  --page <n> / --limit, -n <n> (max 20) / --format json|table|plain

SETUP
  export BRAVE_SEARCH_API_TOKEN=<your key>   (brave.com/search/api)
Results are unverified leads (title + snippet); every client and budget field is null.
`

await runGigCli({ name: "twine-search", help: HELP, search: runSearch, detail: runDetail })
