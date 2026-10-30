#!/usr/bin/env bun
// jobsites-search: regional job boards with no permitted job-seeker API
// (Glints, Kalibrr, ITviec, TokyoDev, SEEK, StepStone, The Hub, Job Bank Canada,
// ...), discovered through the Brave Search API. Boards are never crawled; one
// posting page is read only where sites.ts and robots.txt both allow it.

import { runCli } from "./helpers.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"
import { SITES } from "./sites.ts"

const HELP = `jobsites-search - regional job boards via search-provider discovery

USAGE
  bun run src/cli.ts search [-q "<terms>"] (--site <keys> | --country <code>) [flags]
  bun run src/cli.ts detail <posting URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Search terms. Default: junior flutter developer.
  --site <keys>          Comma list of board keys (below).
  --country <code>       ISO code, e.g. ID, MY, VN, JP, KR, AU, GB, DE, NL, CA.
  --max-sites <n>        Cap on boards queried (one Brave query each). Default 5, max 20.
  --jobage <days>        Brave freshness bucket.
  --page <n> / --limit, -n <n> (max 20) / --format json|table|plain

BOARDS (key  country  detail)
${SITES.map((s) => `  ${s.key.padEnd(18)} ${s.country.padEnd(18)} ${s.fetchable ? "fetch (robots-checked)" : "manual only"}`).join("\n")}

SETUP
  export BRAVE_SEARCH_API_TOKEN=<your key>   (brave.com/search/api)
Search results are unverified leads (snippets). MANUAL_ONLY boards: open the link
in a browser and paste the posting into /apply.
`

await runCli({
  name: "jobsites-search",
  help: HELP,
  searchFlags: [
    { name: "site", type: "string" },
    { name: "country", type: "string" },
    { name: "max-sites", type: "number" },
  ],
  search: (opts) => {
    if (!opts.site && !opts.country) opts.country = "ID"
    return runSearch(opts)
  },
  detail: runDetail,
})
