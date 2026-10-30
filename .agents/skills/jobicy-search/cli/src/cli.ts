#!/usr/bin/env bun
// jobicy-search: the Jobicy public remote-jobs API. Credit Jobicy with a direct
// link to the source listing; Jobicy asks clients not to poll more than hourly.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `jobicy-search - remote jobs from the Jobicy public API

USAGE
  bun run src/cli.ts search [--tag <tag>] [--geo <region>] [-q "<keywords>"] [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --tag <tag>            Jobicy tag/keyword sent to the API, e.g. flutter.
  --geo <region>         Jobicy geo slug, e.g. apac, asia, emea, europe, usa, anywhere.
  --industry <slug>      Jobicy industry slug, e.g. dev, engineering.
  --query, -q <text>     Matched client-side in title + description ("a OR b").
  --jobage <days>        Posted within N days (client-side).
  --page <n> / --limit, -n <n> / --format json|table|plain
`

await runCli({
  name: "jobicy-search",
  help: HELP,
  searchFlags: [
    { name: "tag", type: "string" },
    { name: "geo", type: "string" },
    { name: "industry", type: "string" },
  ],
  search: runSearch,
  detail: runDetail,
})
