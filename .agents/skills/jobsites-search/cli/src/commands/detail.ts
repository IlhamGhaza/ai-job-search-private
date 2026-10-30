import type { Job, Opts } from "../helpers.ts"
import { readPosting } from "../discovery.ts"
import { SITES } from "../sites.ts"
import { PORTAL, UA } from "./search.ts"

/** One posting page via JSON-LD, only for boards marked fetchable in sites.ts and allowed by robots.txt. */
export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  return readPosting(SITES, ref, PORTAL, UA)
}
