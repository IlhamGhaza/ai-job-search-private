#!/usr/bin/env bun
// remotive-search: Remotive's public remote-jobs API. Terms: link back to the
// Remotive URL and credit Remotive as the source; at most ~4 calls a day.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `remotive-search - remote jobs from Remotive's public API

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Keywords (sent to Remotive, then matched client-side:
                         "a b" all words, "a OR b" either).
  --category <slug>      Remotive category. Default software-dev.
  --location, -l <text>  Matched against candidate_required_location, e.g. "worldwide OR asia".
  --jobage <days>        Posted within N days (client-side).
  --page <n> / --limit, -n <n> / --format json|table|plain

Remotive asks API users to call at most ~4 times a day and delays jobs 24h.
Always link to the Remotive URL and name Remotive as the source.
`

await runCli({
  name: "remotive-search",
  help: HELP,
  searchFlags: [
    { name: "category", type: "string" },
    { name: "location", alias: "l", type: "string" },
  ],
  detailFlags: [{ name: "category", type: "string" }],
  search: runSearch,
  detail: runDetail,
})
