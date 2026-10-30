import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, positiveNumber, queryMatcher, userAgent, windowResults, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "remoteok-search"
export const UA = userAgent(PORTAL)

export function apiBase(): string {
  return baseFromEnv("REMOTEOK_API_URL", "https://remoteok.com")
}

type J = Record<string, any>

/** The API's first array element is a legal notice, not a job: skip anything without a position. */
export function parseRemoteOk(body: J[]): Job[] {
  return (Array.isArray(body) ? body : [])
    .filter((j) => j && typeof j === "object" && j.position && j.url)
    .map((j) => {
      const min = positiveNumber(j.salary_min)
      const max = positiveNumber(j.salary_max)
      return makeJob({
        id: String(j.id),
        title: oneLine(j.position) ?? "(untitled)",
        company: oneLine(j.company),
        location: oneLine(j.location),
        date: contractDate(j.date ?? j.epoch),
        url: String(j.url).replace(/^https:\/\/remoteOK\.com/i, "https://remoteok.com"),
        portal: PORTAL,
        // Remote OK publishes salary as USD per year; 0 means not stated.
        salary_min: min,
        salary_max: max,
        salary_currency: min || max ? "USD" : null,
        salary_period: min || max ? "year" : null,
        remote_eligibility: oneLine(j.location),
        work_mode: "remote",
        apply_url: oneLine(j.apply_url),
        evidence: ["Remote OK public API"],
        description: htmlToText(j.description),
      })
    })
}

export async function fetchJobs(tag: string | undefined): Promise<Job[]> {
  const params = tag ? `?tag=${encodeURIComponent(tag)}` : ""
  const body = await getJson<J[]>(`${apiBase()}/api${params}`, { label: "Remote OK API", ua: UA })
  return body ? parseRemoteOk(body) : []
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const jobs = await fetchJobs(opts.tag as string | undefined)
  const match = queryMatcher(opts.query as string | undefined)
  const matchLoc = queryMatcher(opts.location as string | undefined)
  const filtered = jobs.filter((j) => match(`${j.title}\n${j.description ?? ""}`) && matchLoc(j.location ?? ""))
  return { results: windowResults(filtered, opts), total: filtered.length }
}
