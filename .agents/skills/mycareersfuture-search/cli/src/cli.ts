#!/usr/bin/env bun
// mycareersfuture-search: Singapore's government job portal through the JSON
// API its own web app uses (no key). Personal use, low volume.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `mycareersfuture-search - Singapore jobs from MyCareersFuture

USAGE
  bun run src/cli.ts search -q "<keywords>" [flags]
  bun run src/cli.ts detail <uuid|job URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     MyCareersFuture search text, e.g. "flutter".
  --jobage <days>        Posted within N days (client-side on the returned page).
  --page <n>             1-indexed page. Default 1.
  --limit, -n <n>        Results per page (max 100). Default 25.
  --format <fmt>         json (default) | table | plain.

Salary is gross SGD as posted (usually monthly). Singapore roles need a work
pass (Employment Pass / S Pass) for an Indonesian citizen; postings rarely say
whether the employer sponsors one.
`

await runCli({ name: "mycareersfuture-search", help: HELP, search: runSearch, detail: runDetail })
