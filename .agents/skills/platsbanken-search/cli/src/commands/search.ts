import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, userAgent, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "platsbanken-search"
export const UA = userAgent(PORTAL)
export const TOKEN_ENV = "JOBTECH_API_TOKEN"

export function apiBase(): string {
  return baseFromEnv("JOBTECH_API_URL", "https://jobsearch.api.jobtechdev.se")
}

/** JobTech's JobSearch API is open; an api-key header is sent only when the user has one. */
export function headers(): Record<string, string> {
  const token = (process.env[TOKEN_ENV] ?? "").trim()
  return token ? { "api-key": token } : {}
}

type J = Record<string, any>

export function hitToJob(h: J): Job {
  const addr = (h.workplace_address ?? {}) as J
  const model = oneLine(h.workplace_model?.label)
  return makeJob({
    id: String(h.id),
    title: oneLine(h.headline) ?? "(untitled)",
    company: oneLine(h.employer?.name ?? h.employer?.workplace),
    location: [oneLine(addr.municipality), oneLine(addr.region), oneLine(addr.country)].filter(Boolean).join(", ") || null,
    date: contractDate(h.publication_date),
    url: oneLine(h.webpage_url) ?? `https://arbetsformedlingen.se/platsbanken/annonser/${h.id}`,
    portal: PORTAL,
    country: oneLine(addr.country) ?? "Sverige",
    employment_type: [oneLine(h.employment_type?.label), oneLine(h.working_hours_type?.label), oneLine(h.duration?.label)].filter(Boolean).join(", ") || null,
    salary_text: [oneLine(h.salary_type?.label), oneLine(h.salary_description)].filter(Boolean).join(": ") || null,
    work_mode: model ? model.toLowerCase() : null,
    required_experience: h.experience_required === true ? "experience required (no amount stated)" : h.experience_required === false ? "no experience required" : null,
    deadline: contractDate(h.application_deadline),
    apply_url: oneLine(h.application_details?.url),
    evidence: ["JobTech JobSearch API (Platsbanken)"],
    description: htmlToText(h.description?.text_formatted ?? h.description?.text),
  })
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const limit = Math.min((opts.limit as number | undefined) ?? 25, 100)
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  const params = new URLSearchParams({ limit: String(limit), offset: String((page - 1) * limit), sort: "pubdate-desc" })
  // JobSearch treats space-separated words as AND and "a OR b" isn't supported: drop the OR.
  if (opts.query) params.set("q", String(opts.query).replace(/\s+OR\s+/g, " "))
  if (opts.jobage) params.set("published-after", String((opts.jobage as number) * 24 * 60))
  if (opts.remote) params.set("remote", "true")
  const body = await getJson<J>(`${apiBase()}/search?${params}`, { label: "JobTech JobSearch API", ua: UA, headers: headers() })
  const hits = ((body?.hits as J[]) ?? []).map(hitToJob)
  return { results: hits, total: (body?.total?.value as number | undefined) ?? hits.length }
}
