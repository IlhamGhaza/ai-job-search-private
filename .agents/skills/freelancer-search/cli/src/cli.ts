#!/usr/bin/env bun
// freelancer-search: Freelancer.com projects through the official REST API
// (https://www.freelancer.com/api, docs at developers.freelancer.com). Needs
// the user's own OAuth token. Covers freelancer.co.id (same projects).

import { runGigCli } from "./gig.ts"
import { runSearch } from "./commands/search.ts"
import { runDetail } from "./commands/detail.ts"

const HELP = `freelancer-search - Freelancer.com projects (official REST API)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [flags]
  bun run src/cli.ts detail <project id|project URL> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>     Full-text project query. Default "flutter".
  --jobage <days>        Posted within N days (client-side).
  --page <n> / --limit, -n <n> (max 100) / --format json|table|plain

SETUP
  FREELANCER_OAUTH_TOKEN  OAuth access token of your own Freelancer app
                          (accounts.freelancer.com/settings/develop), sent as freelancer-oauth-v1.
Bidding is never automated: /propose fills the bid form and you click Place Bid yourself.
`

await runGigCli({ name: "freelancer-search", help: HELP, search: runSearch, detail: runDetail })
