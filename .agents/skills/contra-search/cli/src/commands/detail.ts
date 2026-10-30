import { manualOnly, type Gig } from "../gig.ts"
import type { Opts } from "../helpers.ts"
import { PLATFORM } from "./search.ts"

/** Contra offers no permitted read API: detail always hands the link back to the user. */
export async function runDetail(ref: string, _opts: Opts): Promise<Gig | null> {
  return manualOnly(PLATFORM, ref)
}
