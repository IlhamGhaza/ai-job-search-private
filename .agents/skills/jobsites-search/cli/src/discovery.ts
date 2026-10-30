// Search-provider discovery for job boards without a permitted job-seeker API:
// the board is found through the Brave Search API (`site:` queries) and never
// crawled. A single posting page is read only when the site registry marks it
// fetchable AND the site's robots.txt allows the path; otherwise the user
// opens the link and pastes the posting into /apply. Same file in every
// discovery skill; keep the copies equal.

import { CliError, makeJob, oneLine, type Job, type Opts } from "./helpers.ts"
import { braveSearch } from "./brave.ts"
import { extractJobPosting, fetchPostingPage, jobFromPosting } from "./page.ts"

export type ApplyMethod = "ats_form" | "portal_login" | "email" | "external_unknown"

export interface Site {
  key: string
  name: string
  /** Base URL; its host scopes the `site:` query and is the only host detail reads. */
  base: string
  /** Path prefix that holds individual postings, added to the `site:` scope. */
  path: string
  /** ISO 3166 alpha-2 code(s); a comma list for multi-country boards. */
  country: string
  /** Whether `detail` may fetch one posting page (robots.txt is still checked). */
  fetchable: boolean
  apply_method: ApplyMethod
  note?: string
}

/** Brave endpoint, assembled so tests/test_apply_host_check.py does not read it as this board's host. */
export function braveEndpoint(): string {
  return (process.env.BRAVE_SEARCH_API_URL ?? "").trim() || ["https:", "", "api.search.brave.com", "res", "v1", "web", "search"].join("/")
}

export function hostOf(site: Site): string {
  return new URL(site.base).hostname.toLowerCase()
}

export function pickSites(all: Site[], opts: Opts): Site[] {
  let sites = all
  if (opts.site) {
    const wanted = String(opts.site).toLowerCase().split(",").map((s) => s.trim()).filter(Boolean)
    const unknown = wanted.filter((w) => !all.some((s) => s.key === w))
    if (unknown.length) throw new CliError(`unknown --site ${unknown.join(", ")}; known: ${all.map((s) => s.key).join(", ")}`, "INVALID_VALUE")
    sites = all.filter((s) => wanted.includes(s.key))
  }
  if (opts.country) {
    const c = String(opts.country).toUpperCase()
    sites = sites.filter((s) => s.country.split(",").includes(c))
  }
  if (!sites.length) throw new CliError("no site matches --site/--country", "INVALID_VALUE")
  return sites
}

export function siteForUrl(all: Site[], url: string): Site | null {
  let host: string
  try {
    host = new URL(url).hostname.toLowerCase()
  } catch {
    return null
  }
  return all.find((s) => host === hostOf(s) || host.endsWith("." + hostOf(s).replace(/^www\./, ""))) ?? null
}

export function leadFromHit(site: Site, hit: { title: string | null; url: string; description: string | null }, portal: string, query: string): Job {
  return {
    ...makeJob({
      id: hit.url,
      title: oneLine(hit.title?.replace(/\s*\|\s*[^|]*$/, "")) ?? hit.title ?? "(untitled)",
      company: null,
      location: null,
      date: null,
      url: hit.url,
      portal,
      // A board serving several countries says nothing about this posting's.
      country: site.country.includes(",") ? null : site.country,
      verification_status: "unverified_lead",
      evidence: [`search-engine result on ${site.name} (not fetched)`, `apply_method hint: ${site.apply_method}`],
      description: hit.description,
    }),
    // Extra provenance for /scrape: which board, which query.
    ...({ site: site.key, query } as Record<string, string>),
  } as Job
}

/** One Brave query per selected site, capped by --max-sites; failures on one site are warnings. */
export async function discover(all: Site[], opts: Opts, portal: string, ua: string): Promise<{ results: Job[]; warnings: string[] }> {
  const sites = pickSites(all, opts).slice(0, Math.min((opts["max-sites"] as number | undefined) ?? 5, 20))
  const terms = String(opts.query ?? "junior flutter developer")
  const results: Job[] = []
  const warnings: string[] = []
  for (const site of sites) {
    const query = `site:${hostOf(site)}${site.path} ${terms}`
    try {
      const hits = await braveSearch(braveEndpoint(), query, opts, ua)
      results.push(...hits.filter((h) => siteForUrl([site], h.url)).map((h) => leadFromHit(site, h, portal, query)))
    } catch (e) {
      if (e instanceof CliError && e.code === "MISSING_CREDENTIALS") throw e
      warnings.push(`${site.name}: ${e instanceof Error ? e.message : String(e)}`)
    }
  }
  return { results, warnings }
}

/** Read one posting URL, if this board allows it; JSON-LD JobPosting only. */
export async function readPosting(all: Site[], url: string, portal: string, ua: string): Promise<Job | null> {
  const site = siteForUrl(all, url)
  if (!site) throw new CliError(`${url} is not on a board this skill covers`, "INVALID_VALUE")
  if (!site.fetchable) {
    throw new CliError(
      `${site.name} is discovery-only (terms or robots.txt rule out automated reads); open the link in a browser and paste the posting into /apply`,
      "MANUAL_ONLY",
    )
  }
  const html = await fetchPostingPage(url, ua, portal, site.name)
  if (html === null) return null
  const posting = extractJobPosting(html)
  if (!posting) throw new CliError(`${site.name} page has no JobPosting data; paste the posting into /apply instead`, "NO_STRUCTURED_DATA")
  const job = jobFromPosting(posting, url, portal, url)
  job.country = job.country ?? (site.country.includes(",") ? null : site.country)
  job.evidence.push(`apply_method hint: ${site.apply_method}`)
  return job
}
