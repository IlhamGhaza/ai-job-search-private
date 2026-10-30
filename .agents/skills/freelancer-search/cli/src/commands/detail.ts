import type { Opts } from "../helpers.ts"
import type { Gig } from "../gig.ts"
import { fetchProject } from "./search.ts"

/** One project through the API (by id or project URL), with its owner's public reputation. */
export async function runDetail(ref: string, _opts: Opts): Promise<Gig | null> {
  return fetchProject(ref)
}
