#!/usr/bin/env bun
// himalayas-search: the Himalayas public remote-jobs search API. Credit
// Himalayas and link to its job URL when sharing results.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `himalayas-search - remote jobs from the Himalayas public API

USAGE
  bun run src/cli.ts search -q "<keywords>" [flags]
  bun run src/cli.ts detail <job URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Himalayas full-text search, e.g. "flutter".
  --title-query <text>   Extra client-side title filter ("junior OR entry OR graduate").
  --country <code>       Himalayas' eligibility filter: jobs open to applicants in this
                         country (ISO code or name, e.g. ID, Indonesia).
  --worldwide            Only jobs Himalayas marks as open worldwide.
  --jobage <days>        Posted within N days (client-side).
  --limit, -n <n>        Max results (one page of up to 20 is fetched).
  --format <fmt>         json (default) | table | plain.

Only page 1 is fetched: Himalayas' robots.txt disallows paging search results.
`

await runCli({
  name: "himalayas-search",
  help: HELP,
  searchFlags: [
    { name: "title-query", type: "string" },
    { name: "country", type: "string" },
    { name: "worldwide", type: "boolean" },
  ],
  search: runSearch,
  detail: runDetail,
})
