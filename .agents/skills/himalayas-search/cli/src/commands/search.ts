import { baseFromEnv, CliError, contractDate, getJson, htmlToText, makeJob, oneLine, payPeriod, positiveNumber, queryMatcher, userAgent, withinDays, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "himalayas-search"
export const UA = userAgent(PORTAL)

export function apiBase(): string {
  return baseFromEnv("HIMALAYAS_API_URL", "https://himalayas.app")
}

type J = Record<string, any>

function list(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => String(x)).filter(Boolean) : []
}

export function parseHimalayas(body: J): Job[] {
  return ((body.jobs as J[]) ?? []).map((j) => {
    const restrictions = list(j.locationRestrictions)
    return makeJob({
      id: String(j.guid ?? j.applicationLink),
      title: oneLine(j.title) ?? "(untitled)",
      company: oneLine(j.companyName),
      location: restrictions.length ? restrictions.join(", ") : "Remote (no location restriction listed)",
      date: contractDate(j.pubDate),
      url: String(j.guid ?? j.applicationLink),
      portal: PORTAL,
      employment_type: oneLine(j.employmentType),
      seniority: list(j.seniority).join(", ") || null,
      salary_min: positiveNumber(j.minSalary),
      salary_max: positiveNumber(j.maxSalary),
      salary_currency: positiveNumber(j.minSalary) || positiveNumber(j.maxSalary) ? (j.currency ?? null) : null,
      salary_period: positiveNumber(j.minSalary) || positiveNumber(j.maxSalary) ? payPeriod(j.salaryPeriod) : null,
      // An empty restriction list is Himalayas' "worldwide"; keep the raw fact.
      remote_eligibility: restrictions.length ? restrictions.join(", ") : "no location restriction listed",
      work_mode: "remote",
      deadline: contractDate(j.expiryDate),
      apply_url: oneLine(j.applicationLink),
      evidence: [
        "Himalayas public API",
        ...(list(j.timezoneRestrictions).length ? [`timezone restrictions: ${list(j.timezoneRestrictions).join(", ")}`] : []),
      ],
      description: htmlToText(j.description) ?? oneLine(j.excerpt),
    })
  })
}

/**
 * Himalayas' robots.txt disallows `/jobs*&page=`, so only the first page of a
 * search is fetched; narrow the query instead of paging.
 */
export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  if (((opts.page as number | undefined) ?? 1) > 1) {
    throw new CliError("Himalayas' robots.txt disallows paging search results; narrow --query or --country instead", "PAGE_DISALLOWED")
  }
  const params = new URLSearchParams()
  if (opts.query) params.set("q", String(opts.query))
  if (opts.country) params.set("country", String(opts.country))
  if (opts.worldwide) params.set("worldwide", "true")
  const body = await getJson<J>(`${apiBase()}/jobs/api/search?${params}`, { label: "Himalayas API", ua: UA })
  const jobs = body ? parseHimalayas(body) : []
  const match = queryMatcher(opts["title-query"] as string | undefined)
  const filtered = jobs.filter((j) => match(j.title) && withinDays(j.date, opts.jobage as number | undefined))
  const limit = (opts.limit as number | undefined) ?? 25
  return { results: filtered.slice(0, limit), total: (body?.totalCount as number | undefined) ?? filtered.length }
}
