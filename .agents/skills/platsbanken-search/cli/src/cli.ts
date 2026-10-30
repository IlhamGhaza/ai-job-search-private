#!/usr/bin/env bun
// platsbanken-search: Sweden's Platsbanken through JobTech's open JobSearch API
// (Arbetsförmedlingen). Open data; an API key is optional.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `platsbanken-search - Swedish jobs (Platsbanken) via the JobTech JobSearch API

USAGE
  bun run src/cli.ts search -q "<keywords>" [flags]
  bun run src/cli.ts detail <ad id|annons URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     JobSearch free text (words are ANDed; "OR" is ignored), e.g. "flutter".
  --remote               Only ads JobTech marks as remote.
  --jobage <days>        Published within N days (server-side).
  --page <n>             1-indexed page. Default 1.
  --limit, -n <n>        Results per page (max 100). Default 25.
  --format <fmt>         json (default) | table | plain.

Ads are mostly in Swedish (sv: utvecklare, apputvecklare, mobilutvecklare).
JOBTECH_API_TOKEN is optional; when set it is sent as the api-key header.
`

await runCli({
  name: "platsbanken-search",
  help: HELP,
  searchFlags: [{ name: "remote", type: "boolean" }],
  search: runSearch,
  detail: runDetail,
})
