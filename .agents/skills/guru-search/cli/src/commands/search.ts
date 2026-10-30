import { discoverGigs, windowGigs, type GigSearchOutcome, type Platform } from "../gig.ts"
import { userAgent, type Opts } from "../helpers.ts"

export const PORTAL = "guru-search"
export const UA = userAgent(PORTAL)
export const HOME = "https://guru.com/"

export const PLATFORM: Platform = {
  portal: PORTAL,
  name: "Guru",
  hosts: ["guru.com"],
  path: "/work/detail",
  apply_method: "platform_bid",
}

/** Search-engine leads only: Guru itself is never requested. */
export async function runSearch(opts: Opts): Promise<GigSearchOutcome> {
  const { results, warnings } = await discoverGigs(PLATFORM, { ...opts, query: opts.query ?? "flutter" }, UA)
  return { results: windowGigs(results, { ...opts, page: 1 }), total: null, warnings }
}
