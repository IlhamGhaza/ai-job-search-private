import { discoverGigs, windowGigs, type GigSearchOutcome, type Platform } from "../gig.ts"
import { userAgent, type Opts } from "../helpers.ts"

export const PORTAL = "projects-co-id-search"
export const UA = userAgent(PORTAL)
export const HOME = "https://projects.co.id/"

export const PLATFORM: Platform = {
  portal: PORTAL,
  name: "Projects.co.id",
  hosts: ["projects.co.id"],
  path: "/public/browse_projects/view",
  apply_method: "platform_bid",
}

/** Search-engine leads only: Projects.co.id itself is never requested. */
export async function runSearch(opts: Opts): Promise<GigSearchOutcome> {
  const { results, warnings } = await discoverGigs(PLATFORM, { ...opts, query: opts.query ?? "flutter" }, UA)
  return { results: windowGigs(results, { ...opts, page: 1 }), total: null, warnings }
}
