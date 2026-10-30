#!/usr/bin/env bun
// ats-search: company career pages through the ATS vendors' official public
// job-board APIs (Greenhouse, Lever, Ashby, Workable, Recruitee). No keys, no
// HTML scraping, zero runtime dependencies. The company list is companies.json.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `ats-search - search company career boards via official public ATS APIs

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [flags] [--format json|table|plain]
  bun run src/cli.ts detail <ats:board:id | posting URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Keywords matched in title + description (client-side).
                         "a b" = all words, "\\"a b\\"" = phrase, "a OR b" = either.
  --title-query <text>   Same syntax, matched against the title only.
  --location, -l <text>  Matched against location/country/work mode, e.g. "remote OR Germany".
  --company <name>       Only companies whose name contains this (or board equals it).
  --ats <name>           greenhouse | lever | ashby | workable | recruitee.
  --companies <file>     Company list to use instead of ../companies.json.
  --jobage <days>        Posted within N days (client-side; undated jobs kept).
  --page <n>             1-indexed page of the filtered list. Default 1.
  --limit, -n <n>        Results per page. Default 25.
  --no-description       Drop descriptions from the output (smaller JSON).
  --format <fmt>         json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "flutter OR dart" --format table
  bun run src/cli.ts search --title-query "mobile OR flutter OR android OR ios" -l "remote" --jobage 14
  bun run src/cli.ts detail greenhouse:canonical:1234567 --format plain

Unsupported: SmartRecruiters (its API robots.txt disallows generic clients),
Workday and in-house career sites (no public job-board API).
`

await runCli({
  name: "ats-search",
  help: HELP,
  searchFlags: [
    { name: "title-query", type: "string" },
    { name: "location", alias: "l", type: "string" },
    { name: "company", type: "string" },
    { name: "ats", type: "string" },
    { name: "companies", type: "string" },
    { name: "no-description", type: "boolean" },
  ],
  search: runSearch,
  detail: runDetail,
})
