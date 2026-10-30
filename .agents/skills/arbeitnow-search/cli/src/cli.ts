#!/usr/bin/env bun
// arbeitnow-search: Arbeitnow's free public job-board API (Germany/EU). Terms:
// do not abuse it; link back to Arbeitnow.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `arbeitnow-search - Germany/EU jobs from the Arbeitnow public API

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [--visa] [--remote] [flags]
  bun run src/cli.ts detail <job URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Matched client-side in title + description ("a OR b").
  --visa                 Ask the API for its visa-sponsorship listings only. Results are
                         tagged as portal-tagged, not as an employer commitment.
  --remote               Ask the API for remote jobs only.
  --location, -l <text>  Matched client-side against the location, e.g. "Berlin OR remote".
  --max-pages <n>        API pages to read (300 jobs each, newest first). Default 2, max 5.
  --jobage <days>        Posted within N days (also stops paging early).
  --page <n> / --limit, -n <n> / --format json|table|plain
`

await runCli({
  name: "arbeitnow-search",
  help: HELP,
  searchFlags: [
    { name: "visa", type: "boolean" },
    { name: "remote", type: "boolean" },
    { name: "location", alias: "l", type: "string" },
    { name: "max-pages", type: "number" },
  ],
  search: runSearch,
  detail: runDetail,
})
