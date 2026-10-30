#!/usr/bin/env bun
// linkedin-posts-search: public LinkedIn hiring posts discovered through the
// Brave Search API. LinkedIn is never fetched or logged into; every result is
// an unverified lead until the job it mentions is found as a real listing.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `linkedin-posts-search - public LinkedIn hiring posts via the Brave Search API

USAGE
  bun run src/cli.ts search [-q "<terms>"] [-l "<place>"] [flags]
  bun run src/cli.ts detail <linkedin.com/posts URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Terms placed after site:linkedin.com/posts, e.g. "\\"junior flutter\\"".
                         Default: junior Flutter developer.
  --location, -l <text>  Adds a quoted place, e.g. Singapore.
  --raw                  Send --query to Brave verbatim (no site: or hiring words added).
  --jobage <days>        Brave freshness bucket (1 day / week / month / year).
  --page <n>             Brave result page (1-10). --limit, -n <n>: up to 20.
  --format <fmt>         json (default) | table | plain.

SETUP
  export BRAVE_SEARCH_API_TOKEN=<your key>   (brave.com/search/api)
Every call is one billed/quota-counted Brave query.
`

await runCli({
  name: "linkedin-posts-search",
  help: HELP,
  searchFlags: [
    { name: "location", alias: "l", type: "string" },
    { name: "raw", type: "boolean" },
  ],
  search: runSearch,
  detail: runDetail,
})
