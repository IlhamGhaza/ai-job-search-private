import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, payPeriod, positiveNumber, queryMatcher, userAgent, windowResults, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "jobicy-search"
export const UA = userAgent(PORTAL)

export function apiBase(): string {
  return baseFromEnv("JOBICY_API_URL", "https://jobicy.com")
}

type J = Record<string, any>

function joined(v: unknown): string | null {
  if (Array.isArray(v)) return v.map((x) => oneLine(x)).filter(Boolean).join(", ") || null
  return oneLine(v)
}

export function parseJobicy(body: J): Job[] {
  return ((body.jobs as J[]) ?? []).map((j) => {
    const min = positiveNumber(j.salaryMin)
    const max = positiveNumber(j.salaryMax)
    return makeJob({
      id: String(j.id),
      title: oneLine(j.jobTitle) ?? "(untitled)",
      company: oneLine(j.companyName),
      location: oneLine(j.jobGeo),
      date: contractDate(j.pubDate),
      url: String(j.url),
      portal: PORTAL,
      employment_type: joined(j.jobType),
      seniority: oneLine(j.jobLevel),
      salary_min: min,
      salary_max: max,
      salary_currency: min || max ? (j.salaryCurrency ?? null) : null,
      salary_period: min || max ? payPeriod(j.salaryPeriod) : null,
      remote_eligibility: oneLine(j.jobGeo),
      work_mode: "remote",
      evidence: ["Jobicy public API"],
      description: htmlToText(j.jobDescription) ?? oneLine(j.jobExcerpt),
    })
  })
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const params = new URLSearchParams({ count: String(Math.min(Math.max(((opts.limit as number) ?? 25) * 2, 20), 100)) })
  if (opts.tag) params.set("tag", String(opts.tag))
  if (opts.geo) params.set("geo", String(opts.geo))
  if (opts.industry) params.set("industry", String(opts.industry))
  const body = await getJson<J>(`${apiBase()}/api/v2/remote-jobs?${params}`, { label: "Jobicy API", ua: UA })
  const jobs = body ? parseJobicy(body) : []
  const match = queryMatcher(opts.query as string | undefined)
  const filtered = jobs.filter((j) => match(`${j.title}\n${j.description ?? ""}`))
  return { results: windowResults(filtered, opts), total: filtered.length }
}
