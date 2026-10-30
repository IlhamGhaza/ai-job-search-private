#!/usr/bin/env bun
// remoteok-search: the Remote OK public JSON API. Terms: link back to the Remote
// OK URL (no nofollow) and credit Remote OK as the source.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `remoteok-search - remote jobs from the Remote OK public API

USAGE
  bun run src/cli.ts search [--tag <tag>] [-q "<keywords>"] [flags]
  bun run src/cli.ts detail <id|url> [--tag <tag>] [--format json|plain]

SEARCH FLAGS
  --tag <tag>            Remote OK tag sent to the API (one tag), e.g. flutter, mobile, dart.
  --query, -q <text>     Matched client-side in title + description ("a OR b", "a b").
  --location, -l <text>  Matched against the location/eligibility text.
  --jobage <days>        Posted within N days (client-side).
  --page <n> / --limit, -n <n> / --format json|table|plain

Salary, when stated, is USD per year (the API's convention). Credit Remote OK
and link to its URL when sharing results.
`

await runCli({
  name: "remoteok-search",
  help: HELP,
  searchFlags: [
    { name: "tag", type: "string" },
    { name: "location", alias: "l", type: "string" },
  ],
  detailFlags: [{ name: "tag", type: "string" }],
  search: runSearch,
  detail: runDetail,
})
