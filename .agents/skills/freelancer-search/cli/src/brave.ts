// Discovery through the Brave Search API (a documented, keyed web-search API):
// the portal itself is never crawled. A search hit is a lead, not a verified
// posting - callers mark it `unverified_lead` until the posting is fetched.
// Same file in every discovery skill; keep the copies equal.

import { CliError, getJson, oneLine, type Opts } from "./helpers.ts"

export const BRAVE_TOKEN_ENV = "BRAVE_SEARCH_API_TOKEN"

export interface BraveHit {
  title: string | null
  url: string
  description: string | null
  age: string | null
  page_age: string | null
}

interface BraveResponse {
  web?: { results?: Array<{ title?: string; url?: string; description?: string; age?: string; page_age?: string }> }
}

/** Brave's freshness bucket for a max posting age in days. */
export function freshness(days: number | undefined): string | undefined {
  if (!days) return undefined
  if (days <= 1) return "pd"
  if (days <= 7) return "pw"
  if (days <= 31) return "pm"
  return "py"
}

/** Read the API token from the environment only; never a flag, never logged. */
export function braveToken(): string {
  const token = (process.env[BRAVE_TOKEN_ENV] ?? "").trim()
  if (!token) {
    throw new CliError(
      `${BRAVE_TOKEN_ENV} is not set. Get a key at brave.com/search/api and export it; see this skill's SKILL.md Setup section.`,
      "MISSING_CREDENTIALS",
    )
  }
  return token
}

/**
 * One Brave web search. `endpoint` is passed in by the skill. Brave allows at
 * most 20 results per call and offsets 0-9; the CLI maps --page onto offset.
 */
export async function braveSearch(endpoint: string, query: string, opts: Opts, ua: string): Promise<BraveHit[]> {
  const token = braveToken()
  const params = new URLSearchParams({ q: query, count: String(Math.min((opts.limit as number | undefined) ?? 20, 20)) })
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  if (page > 10) throw new CliError("Brave Search serves at most 10 pages per query", "INVALID_VALUE")
  if (page > 1) params.set("offset", String(page - 1))
  const fresh = freshness(opts.jobage as number | undefined)
  if (fresh) params.set("freshness", fresh)
  const body = await getJson<BraveResponse>(`${endpoint}?${params}`, {
    label: "Brave Search API",
    ua,
    headers: { "X-Subscription-Token": token },
  })
  return (body?.web?.results ?? [])
    .filter((r) => typeof r.url === "string" && /^https?:\/\//.test(r.url))
    .map((r) => ({
      title: oneLine(r.title),
      url: r.url as string,
      description: oneLine(r.description),
      age: r.age ?? null,
      page_age: r.page_age ?? null,
    }))
}
