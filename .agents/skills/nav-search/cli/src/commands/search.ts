import { baseFromEnv, CliError, contractDate, getJson, htmlToText, httpGet, makeJob, oneLine, queryMatcher, userAgent, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "nav-search"
export const UA = userAgent(PORTAL)
export const TOKEN_ENV = "NAV_API_TOKEN"

export function apiBase(): string {
  return baseFromEnv("NAV_FEED_URL", "https://pam-stilling-feed.nav.no")
}

/**
 * NAV_API_TOKEN when set (a personal consumer token from NAV); otherwise the
 * public token NAV publishes at /api/publicToken for exactly this use.
 */
export async function token(): Promise<string> {
  const own = (process.env[TOKEN_ENV] ?? "").trim()
  if (own) return own
  const text = await httpGet(`${apiBase()}/api/publicToken`, { label: "NAV public token endpoint", ua: UA, accept: "text/plain" })
  const jwt = text?.match(/[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/)?.[0]
  if (!jwt) throw new CliError(`NAV published no public token; set ${TOKEN_ENV} to a consumer token`, "MISSING_CREDENTIALS")
  return jwt
}

type J = Record<string, any>

export function adToJob(entry: J): Job {
  const ad = (entry.ad_content ?? entry) as J
  const loc = ((ad.workLocations as J[]) ?? [])[0] ?? {}
  return makeJob({
    id: String(ad.uuid ?? entry.uuid),
    title: oneLine(ad.title) ?? "(untitled)",
    company: oneLine(ad.employer?.name),
    location: [oneLine(loc.city), oneLine(loc.county), oneLine(loc.country)].filter(Boolean).join(", ") || null,
    date: contractDate(ad.published),
    url: oneLine(ad.link) ?? `https://arbeidsplassen.nav.no/stillinger/stilling/${ad.uuid}`,
    portal: PORTAL,
    country: oneLine(loc.country),
    employment_type: [oneLine(ad.engagementtype), oneLine(ad.extent)].filter(Boolean).join(", ") || null,
    deadline: contractDate(ad.applicationDue ?? ad.expires),
    apply_url: oneLine(ad.applicationUrl),
    evidence: ["NAV job vacancy feed (arbeidsplassen.no)"],
    // Contact persons are deliberately not copied: the workflow never needs them.
    description: htmlToText(ad.description),
  })
}

export interface FeedItem {
  uuid: string
  title: string
  business: string
  status: string
}

export function parseFeedPage(body: J): { items: FeedItem[]; next: string | null } {
  const items = ((body.items as J[]) ?? []).map((i) => ({
    uuid: String(i._feed_entry?.uuid ?? i.id),
    title: oneLine(i._feed_entry?.title ?? i.title) ?? "",
    business: oneLine(i._feed_entry?.businessName) ?? "",
    status: String(i._feed_entry?.status ?? "ACTIVE"),
  }))
  return { items, next: typeof body.next_url === "string" && body.next_url ? body.next_url : null }
}

/**
 * The feed is change-ordered with no keyword search: read pages changed within
 * --jobage days (If-Modified-Since), match titles client-side, then fetch the
 * full ad only for matches.
 */
export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  if (!opts.query) throw new CliError("nav-search needs --query (titles are matched client-side)", "MISSING_VALUE")
  const auth = { Authorization: `Bearer ${await token()}` }
  const days = (opts.jobage as number | undefined) ?? 7
  const since = new Date(Date.now() - days * 86_400_000).toUTCString()
  const maxPages = Math.min((opts["max-pages"] as number | undefined) ?? 5, 20)
  // Norwegian compounds ("Systemutvikler"): match inside words.
  const match = queryMatcher(opts.query as string, true)
  const limit = (opts.limit as number | undefined) ?? 25
  const hits = new Map<string, FeedItem>()
  let path: string | null = "/api/v1/feed"
  for (let page = 0; page < maxPages && path; page++) {
    const body: J | null = await getJson<J>(`${apiBase()}${path}`, {
      label: "NAV job feed",
      ua: UA,
      headers: page === 0 ? { ...auth, "If-Modified-Since": since } : auth,
    })
    if (!body) break
    const { items, next } = parseFeedPage(body)
    for (const it of items) {
      if (it.status === "ACTIVE" && match(`${it.title} ${it.business}`)) hits.set(it.uuid, it)
      else if (it.status !== "ACTIVE") hits.delete(it.uuid)
    }
    path = next
  }
  const results: Job[] = []
  for (const it of [...hits.values()].slice(0, limit)) {
    const entry = await getJson<J>(`${apiBase()}/api/v1/feedentry/${encodeURIComponent(it.uuid)}`, { label: "NAV job feed", ua: UA, headers: auth })
    if (entry && entry.status !== "INACTIVE") results.push(adToJob(entry))
  }
  results.sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""))
  return { results, total: hits.size }
}
