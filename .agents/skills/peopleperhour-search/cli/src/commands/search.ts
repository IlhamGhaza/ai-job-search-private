import { discoverGigs, windowGigs, type GigSearchOutcome, type Platform } from "../gig.ts"
import { userAgent, type Opts } from "../helpers.ts"

export const PORTAL = "peopleperhour-search"
export const UA = userAgent(PORTAL)
export const HOME = "https://peopleperhour.com/"

export const PLATFORM: Platform = {
  portal: PORTAL,
  name: "PeoplePerHour",
  hosts: ["peopleperhour.com"],
  path: "/freelance-jobs",
  apply_method: "platform_proposal",
}

/** Search-engine leads only: PeoplePerHour itself is never requested. */
export async function runSearch(opts: Opts): Promise<GigSearchOutcome> {
  const { results, warnings } = await discoverGigs(PLATFORM, { ...opts, query: opts.query ?? "flutter" }, UA)
  return { results: windowGigs(results, { ...opts, page: 1 }), total: null, warnings }
}
