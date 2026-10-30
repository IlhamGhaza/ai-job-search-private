#!/usr/bin/env bun
// nav-search: Norway's public job vacancy feed (pam-stilling-feed, NAV /
// arbeidsplassen.no). Read-only, with NAV's published public token or your own.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `nav-search - Norwegian jobs from NAV's public job vacancy feed

USAGE
  bun run src/cli.ts search -q "<title keywords>" [flags]
  bun run src/cli.ts detail <uuid|arbeidsplassen URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Required. Matched client-side against titles and employer names
                         ("flutter OR mobilutvikler OR apputvikler").
  --jobage <days>        Feed entries changed within N days. Default 7.
  --max-pages <n>        Feed pages to read (1000 entries each). Default 5, max 20.
  --limit, -n <n>        Max ads to fetch in full. Default 25.
  --format <fmt>         json (default) | table | plain.

NAV_API_TOKEN (optional): your own feed consumer token. Without it the CLI
uses the public token NAV publishes at /api/publicToken. Ads are mostly in Norwegian.
`

await runCli({
  name: "nav-search",
  help: HELP,
  searchFlags: [{ name: "max-pages", type: "number" }],
  search: runSearch,
  detail: runDetail,
})
