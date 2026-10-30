import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, queryMatcher, userAgent, withinDays, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "arbeitnow-search"
export const UA = userAgent(PORTAL)

export function apiBase(): string {
  return baseFromEnv("ARBEITNOW_API_URL", "https://www.arbeitnow.com")
}

type J = Record<string, any>

/**
 * `visaFilter` records that the page was requested with the API's
 * visa_sponsorship=true filter: the response itself carries no per-job flag,
 * so this is the portal's tag, not the employer's written commitment.
 */
export function parseArbeitnow(body: J, visaFilter: boolean): Job[] {
  return ((body.data as J[]) ?? []).map((j) => {
    const types = Array.isArray(j.job_types) ? j.job_types.map((t: unknown) => oneLine(t)).filter(Boolean).join(", ") : null
    return makeJob({
      id: String(j.slug),
      title: oneLine(j.title) ?? "(untitled)",
      company: oneLine(j.company_name),
      location: oneLine(j.location),
      date: contractDate(j.created_at),
      url: String(j.url),
      portal: PORTAL,
      country: null,
      employment_type: types || null,
      work_mode: j.remote === true ? "remote" : null,
      visa_sponsorship: visaFilter ? "tagged by Arbeitnow's visa-sponsorship filter (unconfirmed by employer text)" : null,
      evidence: ["Arbeitnow public job-board API", ...(visaFilter ? ["listed under visa_sponsorship=true"] : [])],
      description: htmlToText(j.description),
    })
  })
}

/**
 * The API pages 300 newest-first jobs per call with no keyword search, so the
 * CLI reads up to --max-pages pages and filters client-side.
 */
export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const visa = Boolean(opts.visa)
  const maxPages = Math.min((opts["max-pages"] as number | undefined) ?? 2, 5)
  const match = queryMatcher(opts.query as string | undefined)
  const matchLoc = queryMatcher(opts.location as string | undefined)
  const pool: Job[] = []
  for (let page = 1; page <= maxPages; page++) {
    const params = new URLSearchParams({ page: String(page) })
    if (visa) params.set("visa_sponsorship", "true")
    if (opts.remote) params.set("remote", "true")
    const body = await getJson<J>(`${apiBase()}/api/job-board-api?${params}`, { label: "Arbeitnow API", ua: UA })
    if (!body) break
    const jobs = parseArbeitnow(body, visa)
    pool.push(...jobs)
    const oldest = jobs[jobs.length - 1]?.date ?? null
    if (!body.links?.next || !withinDays(oldest, opts.jobage as number | undefined)) break
  }
  const filtered = pool.filter(
    (j) => match(`${j.title}\n${j.description ?? ""}`) && matchLoc(`${j.location ?? ""} ${j.work_mode ?? ""}`) && withinDays(j.date, opts.jobage as number | undefined),
  )
  const limit = (opts.limit as number | undefined) ?? 25
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  return { results: filtered.slice((page - 1) * limit, page * limit), total: filtered.length }
}
