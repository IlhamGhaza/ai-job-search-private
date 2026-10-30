import { userAgent, type Opts, type SearchOutcome } from "../helpers.ts"
import { discover } from "../discovery.ts"
import { SITES } from "../sites.ts"

export const PORTAL = "jobstreet-search"
export const UA = userAgent(PORTAL)

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const { results, warnings } = await discover(SITES, opts, PORTAL, UA)
  return { results, total: null, warnings }
}
