#!/usr/bin/env bun
// jobstreet-search: JobStreet postings (ID, MY, PH, SG) discovered through the
// Brave Search API. JobStreet itself is never fetched: SEEK offers no job-seeker
// API and its robots.txt disallows job pages. Coverage is partial by design.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `jobstreet-search - JobStreet postings via search-provider discovery (partial coverage)

USAGE
  bun run src/cli.ts search [-q "<terms>"] [--site id,my,ph,sg] [flags]
  bun run src/cli.ts detail <url>     (always MANUAL_ONLY: open it and paste into /apply)

SEARCH FLAGS
  --query, -q <text>     Search terms. Default: junior flutter developer.
  --site <keys>          id, my, ph, sg (comma list). Default all four.
  --country <code>       ID | MY | PH | SG (alternative to --site).
  --max-sites <n>        Cap on sites queried (one Brave query each). Default 5.
  --jobage <days>        Brave freshness bucket.
  --page <n> / --limit, -n <n> (max 20) / --format json|table|plain

SETUP
  export BRAVE_SEARCH_API_TOKEN=<your key>   (brave.com/search/api)
Results are unverified leads (search snippets), never confirmed postings.
`

await runCli({
  name: "jobstreet-search",
  help: HELP,
  searchFlags: [
    { name: "site", type: "string" },
    { name: "country", type: "string" },
    { name: "max-sites", type: "number" },
  ],
  search: runSearch,
  detail: runDetail,
})
