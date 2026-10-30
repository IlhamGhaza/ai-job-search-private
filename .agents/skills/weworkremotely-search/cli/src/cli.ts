#!/usr/bin/env bun
// weworkremotely-search: We Work Remotely's public RSS feeds (one request per
// search). Link back to the WWR listing when sharing results.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `weworkremotely-search - remote jobs from We Work Remotely's RSS feeds

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [--category <slug>] [flags]
  bun run src/cli.ts detail <job URL|slug> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Matched client-side in title + description ("a OR b").
  --category <slug>      Feed: remote-programming-jobs (default), remote-full-stack-programming-jobs,
                         remote-front-end-programming-jobs, remote-back-end-programming-jobs,
                         or "all" for every category.
  --location, -l <text>  Matched against the <region> eligibility text, e.g. "anywhere OR asia".
  --jobage <days>        Posted within N days (client-side).
  --page <n> / --limit, -n <n> / --format json|table|plain
`

await runCli({
  name: "weworkremotely-search",
  help: HELP,
  searchFlags: [
    { name: "category", type: "string" },
    { name: "location", alias: "l", type: "string" },
  ],
  detailFlags: [{ name: "category", type: "string" }],
  search: runSearch,
  detail: runDetail,
})
