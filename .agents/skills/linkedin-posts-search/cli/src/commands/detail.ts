import { CliError, type Job, type Opts } from "../helpers.ts"
import { braveSearch } from "../brave.ts"
import { endpoint, hitToLead, isPostUrl, UA } from "./search.ts"

/**
 * LinkedIn itself is never fetched (its terms forbid automated access and posts
 * sit behind a login): detail re-asks the search engine for that exact URL and
 * returns the refreshed snippet, still an unverified lead.
 */
export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  if (!isPostUrl(ref)) throw new CliError("pass a public linkedin.com/posts/... URL from a search result", "INVALID_VALUE")
  const query = `"${ref}"`
  const hits = await braveSearch(endpoint(), query, { limit: 5 }, UA)
  const hit = hits.find((h) => h.url.split("?")[0] === ref.split("?")[0])
  return hit ? hitToLead(hit, query) : null
}
