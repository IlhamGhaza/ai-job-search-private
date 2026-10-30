import { discoverGigs, windowGigs, type GigSearchOutcome, type Platform } from "../gig.ts"
import { userAgent, type Opts } from "../helpers.ts"

export const PORTAL = "twine-search"
export const UA = userAgent(PORTAL)
export const HOME = "https://twine.net/"

export const PLATFORM: Platform = {
  portal: PORTAL,
  name: "Twine",
  hosts: ["twine.net"],
  path: "/projects",
  apply_method: "platform_proposal",
}

/** Search-engine leads only: Twine itself is never requested. */
export async function runSearch(opts: Opts): Promise<GigSearchOutcome> {
  const { results, warnings } = await discoverGigs(PLATFORM, { ...opts, query: opts.query ?? "flutter" }, UA)
  return { results: windowGigs(results, { ...opts, page: 1 }), total: null, warnings }
}
