import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, payPeriod, positiveNumber, userAgent, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "mycareersfuture-search"
export const UA = userAgent(PORTAL)

export function apiBase(): string {
  return baseFromEnv("MCF_API_URL", "https://api.mycareersfuture.gov.sg")
}

type J = Record<string, any>

function labels(v: unknown, key: string): string | null {
  return Array.isArray(v) ? v.map((x) => oneLine((x as J)?.[key])).filter(Boolean).join(", ") || null : null
}

export function mcfToJob(j: J): Job {
  const salary = (j.salary ?? {}) as J
  const hidden = j.metadata?.isHideSalary === true
  const addr = (j.address ?? {}) as J
  const overseas = addr.isOverseas === true ? oneLine(addr.overseasCountry) : null
  const district = ((addr.districts as J[]) ?? []).map((d) => oneLine(d.location)).filter(Boolean).join(", ")
  const years = positiveNumber(j.minimumYearsExperience)
  const remote = labels(j.flexibleWorkArrangements, "flexibleWorkArrangement")
  return makeJob({
    id: String(j.uuid),
    title: oneLine(j.title) ?? "(untitled)",
    company: oneLine(j.postedCompany?.name ?? j.hiringCompany?.name),
    location: overseas ?? (district ? `${district}, Singapore` : "Singapore"),
    date: contractDate(j.metadata?.newPostingDate ?? j.metadata?.originalPostingDate),
    url: oneLine(j.metadata?.jobDetailsUrl) ?? `https://www.mycareersfuture.gov.sg/job/${j.uuid}`,
    portal: PORTAL,
    country: overseas ?? "Singapore",
    employment_type: labels(j.employmentTypes, "employmentType"),
    seniority: labels(j.positionLevels, "position"),
    salary_min: hidden ? null : positiveNumber(salary.minimum),
    salary_max: hidden ? null : positiveNumber(salary.maximum),
    salary_currency: !hidden && (salary.minimum || salary.maximum) ? "SGD" : null,
    salary_period: !hidden ? payPeriod(salary.type?.salaryType) : null,
    // MCF salaries are gross monthly pay as posted by the employer.
    salary_gross_or_net: !hidden && (salary.minimum || salary.maximum) ? "gross" : null,
    work_mode: remote ? remote.toLowerCase() : null,
    required_experience: years !== null ? `${years}+ years` : j.minimumYearsExperience === 0 ? "0 years" : null,
    deadline: contractDate(j.metadata?.expiryDate),
    evidence: ["MyCareersFuture job search API (Singapore Government)"],
    description: htmlToText(j.description),
  })
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const limit = Math.min((opts.limit as number | undefined) ?? 25, 100)
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  const params = new URLSearchParams({ search: String(opts.query ?? ""), limit: String(limit), page: String(page - 1), sortBy: "new_posting_date" })
  const body = await getJson<J>(`${apiBase()}/v2/jobs?${params}`, { label: "MyCareersFuture API", ua: UA })
  let results = ((body?.results as J[]) ?? []).map(mcfToJob)
  if (opts.jobage) {
    const cutoff = Date.now() - (opts.jobage as number) * 86_400_000
    results = results.filter((r) => !r.date || Date.parse(r.date) >= cutoff - 86_400_000)
  }
  return { results, total: (body?.total as number | undefined) ?? results.length }
}
