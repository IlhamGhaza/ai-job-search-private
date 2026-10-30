import type { Job, Opts } from "../helpers.ts"
import { readPosting } from "../discovery.ts"
import { SITES } from "../sites.ts"
import { PORTAL, UA } from "./search.ts"

/** Always MANUAL_ONLY for JobStreet (see sites.ts); kept so the contract's detail command exists. */
export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  return readPosting(SITES, ref, PORTAL, UA)
}
