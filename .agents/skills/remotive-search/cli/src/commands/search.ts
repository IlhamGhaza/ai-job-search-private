import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, queryMatcher, userAgent, windowResults, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "remotive-search"
export const UA = userAgent(PORTAL)

/** API base; REMOTIVE_API_URL overrides it (tests, mirrors). */
export function apiBase(): string {
  return baseFromEnv("REMOTIVE_API_URL", "https://remotive.com")
}

type J = Record<string, any>

/** Remotive's job_type vocabulary to plain words. */
function jobType(v: unknown): string | null {
  const s = oneLine(v)
  return s ? s.replace(/_/g, "-") : null
}

export function parseRemotive(body: J): Job[] {
  return ((body.jobs as J[]) ?? []).map((j) =>
    makeJob({
      id: String(j.id),
      title: oneLine(j.title) ?? "(untitled)",
      company: oneLine(j.company_name),
      location: oneLine(j.candidate_required_location),
      date: contractDate(j.publication_date),
      url: String(j.url),
      portal: PORTAL,
      employment_type: jobType(j.job_type),
      salary_text: oneLine(j.salary),
      remote_eligibility: oneLine(j.candidate_required_location),
      work_mode: "remote",
      evidence: ["Remotive public API (jobs are delayed 24h by Remotive)"],
      description: htmlToText(j.description),
    }),
  )
}

/** One API call; Remotive asks for at most ~4 calls a day, so the CLI never pages server-side. */
export async function fetchJobs(opts: Opts): Promise<Job[]> {
  const params = new URLSearchParams()
  // An OR query cannot be expressed in Remotive's `search`; read the whole
  // category instead and let the client-side matcher do the OR.
  if (opts.query && !/\sOR\s/.test(String(opts.query))) params.set("search", String(opts.query))
  params.set("category", String(opts.category ?? "software-dev"))
  const body = await getJson<J>(`${apiBase()}/api/remote-jobs?${params}`, { label: "Remotive API", ua: UA })
  return body ? parseRemotive(body) : []
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const jobs = await fetchJobs(opts)
  // Remotive's `search` is a loose OR over words; tighten to the documented query syntax.
  const match = queryMatcher(opts.query as string | undefined)
  const matchLoc = queryMatcher(opts.location as string | undefined)
  const filtered = jobs.filter((j) => match(`${j.title}\n${j.description ?? ""}`) && matchLoc(j.remote_eligibility ?? ""))
  return { results: windowResults(filtered, opts), total: filtered.length }
}
