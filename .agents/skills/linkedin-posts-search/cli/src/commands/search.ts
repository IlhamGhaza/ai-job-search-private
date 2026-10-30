import { makeJob, userAgent, type Job, type Opts, type SearchOutcome } from "../helpers.ts"
import { braveSearch, type BraveHit } from "../brave.ts"

export const PORTAL = "linkedin-posts-search"
export const UA = userAgent(PORTAL)

/** Brave Search web endpoint; BRAVE_SEARCH_API_URL overrides it for the offline tests. */
export function endpoint(): string {
  return (process.env.BRAVE_SEARCH_API_URL ?? "").trim() || "https://api.search.brave.com/res/v1/web/search"
}

/** Public post URLs only: /posts/ and /feed/update/ on a linkedin.com host. Never fetched. */
export function isPostUrl(url: string): boolean {
  try {
    const u = new URL(url)
    const host = u.hostname.toLowerCase()
    return (host === "linkedin.com" || host.endsWith(".linkedin.com")) && /^\/(posts|feed\/update)\//.test(u.pathname)
  } catch {
    return false
  }
}

/** The search-engine query: site-scoped, the user's terms, a hiring word, optional location. */
export function buildQuery(opts: Opts): string {
  if (opts.raw) return String(opts.query ?? "")
  const terms = String(opts.query ?? "junior Flutter developer")
  const location = opts.location ? ` "${String(opts.location)}"` : ""
  return `site:linkedin.com/posts ${terms} (hiring OR "we are hiring" OR "join our team")${location}`
}

export type PostLead = Job & { query: string; snippet: string | null; poster: string | null; discovered_at: string }

export function hitToLead(hit: BraveHit, query: string, now = new Date()): PostLead {
  const poster = hit.title?.match(/^(.+?) on LinkedIn\b/)?.[1]?.trim() ?? hit.title?.match(/^(.+?)'s Post\b/)?.[1]?.trim() ?? null
  const job = makeJob({
    id: hit.url,
    title: hit.title ?? "(LinkedIn post)",
    // The poster may be a person or a recruiter, not the employer: company stays unknown.
    company: null,
    location: null,
    date: null,
    url: hit.url,
    portal: PORTAL,
    source_type: "social_post",
    verification_status: "unverified_lead",
    evidence: ["search-engine snippet of a public LinkedIn post (not a verified job listing)"],
    description: hit.description,
  })
  return { ...job, query, snippet: hit.description, poster, discovered_at: now.toISOString() }
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const query = buildQuery(opts)
  const hits = await braveSearch(endpoint(), query, opts, UA)
  const results = hits.filter((h) => isPostUrl(h.url)).map((h) => hitToLead(h, query))
  return { results, total: null }
}
