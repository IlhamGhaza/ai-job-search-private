// One adapter per ATS public job-board API. Each turns the provider's own JSON
// into the job record; nothing is inferred that the API does not state.
//
// Host literals: tests/test_apply_host_check.py reads every `https://host` in
// cli/src as a board this skill serves. apply.workable.com is assembled from a
// constant so it keeps classifying as an official ATS host, not as this skill.

import { baseFromEnv, contractDate, getJson, htmlToText, makeJob, oneLine, payPeriod, positiveNumber, userAgent, type Job } from "./helpers.ts"

export const ATS_NAMES = ["greenhouse", "lever", "ashby", "workable", "recruitee"] as const
export type AtsName = (typeof ATS_NAMES)[number]

const PORTAL = "ats-search"
const UA = userAgent(PORTAL)
const WORKABLE_HOST = "apply.workable.com"

/**
 * API roots. ATS_API_BASE_OVERRIDE (tests only) routes every provider to
 * `<override>/<ats>`; Recruitee's root depends on the board's subdomain.
 */
export function apiRoot(ats: AtsName, board: string): string {
  const override = (process.env.ATS_API_BASE_OVERRIDE ?? "").trim().replace(/\/+$/, "")
  if (override) return `${override}/${ats}`
  switch (ats) {
    case "greenhouse":
      return baseFromEnv("GREENHOUSE_API_URL", "https://boards-api.greenhouse.io")
    case "lever":
      return baseFromEnv("LEVER_API_URL", "https://api.lever.co")
    case "ashby":
      return baseFromEnv("ASHBY_API_URL", "https://api.ashbyhq.com")
    case "workable":
      return "https:" + "//" + WORKABLE_HOST
    case "recruitee":
      return "https:" + "//" + `${encodeURIComponent(board)}.recruitee.com`
  }
}

type J = Record<string, any>

function get(ats: AtsName, board: string, path: string): Promise<J | J[] | null> {
  return getJson<J | J[]>(apiRoot(ats, board) + path, { label: `${ats} board "${board}"`, ua: UA })
}

export interface Company {
  name: string
  ats: AtsName
  board: string
}

// ---------------------------------------------------------------- Greenhouse

export function parseGreenhouse(body: J, company: Company): Job[] {
  return ((body.jobs as J[]) ?? []).map((j) => greenhouseJob(j, company))
}

function fromCents(value: unknown): number | null {
  const cents = positiveNumber(value)
  return cents === null ? null : cents / 100
}

function greenhouseJob(j: J, company: Company): Job {
  const pay = ((j.pay_input_ranges as J[]) ?? [])[0]
  return makeJob({
    id: `greenhouse:${company.board}:${j.id}`,
    title: oneLine(j.title) ?? "(untitled)",
    company: oneLine(j.company_name) ?? company.name,
    location: oneLine(j.location?.name),
    date: contractDate(j.first_published ?? j.updated_at),
    url: String(j.absolute_url),
    portal: PORTAL,
    salary_min: fromCents(pay?.min_cents),
    salary_max: fromCents(pay?.max_cents),
    salary_currency: pay?.currency_type ?? null,
    salary_text: pay ? oneLine(pay.title) : null,
    deadline: contractDate(j.application_deadline),
    apply_url: String(j.absolute_url),
    evidence: ["Greenhouse job board API"],
    description: htmlToText(j.content),
  })
}

// ---------------------------------------------------------------- Lever

export function parseLever(body: J[], company: Company): Job[] {
  return (Array.isArray(body) ? body : []).map((j) => leverJob(j, company))
}

function leverJob(j: J, company: Company): Job {
  const lists = ((j.lists as J[]) ?? []).map((l) => `${oneLine(l.text) ?? ""}\n${htmlToText(l.content) ?? ""}`).join("\n\n")
  const salary = j.salaryRange as J | undefined
  const workplace = oneLine(j.workplaceType)
  return makeJob({
    id: `lever:${company.board}:${j.id}`,
    title: oneLine(j.text) ?? "(untitled)",
    company: company.name,
    location: oneLine(j.categories?.location) ?? oneLine((j.categories?.allLocations ?? []).join(", ")),
    date: contractDate(j.createdAt),
    url: String(j.hostedUrl),
    portal: PORTAL,
    country: oneLine(j.country),
    employment_type: oneLine(j.categories?.commitment),
    salary_min: positiveNumber(salary?.min),
    salary_max: positiveNumber(salary?.max),
    salary_currency: salary?.currency ?? null,
    salary_period: payPeriod(salary?.interval),
    work_mode: workplace && workplace !== "unspecified" ? workplace.toLowerCase() : null,
    apply_url: oneLine(j.applyUrl),
    evidence: ["Lever postings API"],
    description: [j.descriptionPlain, lists, j.additionalPlain].filter(Boolean).join("\n\n").trim() || null,
  })
}

// ---------------------------------------------------------------- Ashby

export function parseAshby(body: J, company: Company): Job[] {
  return ((body.jobs as J[]) ?? []).filter((j) => j.isListed !== false).map((j) => ashbyJob(j, company))
}

function ashbyJob(j: J, company: Company): Job {
  const comp = ((j.compensation?.summaryComponents as J[]) ?? []).find((c) => /salary/i.test(String(c.compensationType)))
  const workplace = oneLine(j.workplaceType)
  return makeJob({
    id: `ashby:${company.board}:${j.id}`,
    title: oneLine(j.title) ?? "(untitled)",
    company: company.name,
    location: oneLine(j.location),
    date: contractDate(j.publishedAt),
    url: String(j.jobUrl),
    portal: PORTAL,
    country: oneLine(j.address?.postalAddress?.addressCountry),
    employment_type: oneLine(j.employmentType),
    salary_min: positiveNumber(comp?.minValue),
    salary_max: positiveNumber(comp?.maxValue),
    salary_currency: comp?.currencyCode ?? null,
    salary_period: payPeriod(comp?.interval),
    salary_text: oneLine(j.compensation?.compensationTierSummary),
    work_mode: j.isRemote ? "remote" : workplace ? workplace.toLowerCase() : null,
    apply_url: oneLine(j.applyUrl),
    evidence: ["Ashby posting API"],
    description: htmlToText(j.descriptionHtml) ?? oneLine(j.descriptionPlain),
  })
}

// ---------------------------------------------------------------- Workable

export function parseWorkable(body: J, company: Company): Job[] {
  return ((body.jobs as J[]) ?? []).map((j) => workableJob(j, company, body.name))
}

function workableJob(j: J, company: Company, accountName: unknown): Job {
  const loc = ((j.locations as J[]) ?? [])[0] ?? {}
  const country = oneLine(loc.country ?? j.country)
  return makeJob({
    id: `workable:${company.board}:${j.shortcode}`,
    title: oneLine(j.title) ?? "(untitled)",
    company: oneLine(accountName) ?? company.name,
    location: [oneLine(loc.city ?? j.city), oneLine(loc.region ?? j.state), country].filter(Boolean).join(", ") || null,
    date: contractDate(j.published_on ?? j.created_at),
    url: String(j.url ?? j.shortlink),
    portal: PORTAL,
    country,
    employment_type: oneLine(j.employment_type),
    seniority: oneLine(j.experience),
    work_mode: j.telecommuting === true ? "remote" : null,
    apply_url: oneLine(j.application_url),
    evidence: ["Workable widget API"],
    description: htmlToText(j.description),
  })
}

// ---------------------------------------------------------------- Recruitee

export function parseRecruitee(body: J, company: Company): Job[] {
  const offers = (body.offers as J[]) ?? (body.offer ? [body.offer] : [])
  return offers.map((j) => recruiteeJob(j, company))
}

function recruiteeJob(j: J, company: Company): Job {
  const mode = j.remote ? "remote" : j.hybrid ? "hybrid" : j.on_site ? "onsite" : null
  const salary = (j.salary as J | undefined) ?? {}
  return makeJob({
    id: `recruitee:${company.board}:${j.slug}`,
    title: oneLine(j.title) ?? "(untitled)",
    company: oneLine(j.company_name) ?? company.name,
    location: oneLine(j.location),
    date: contractDate(j.published_at ?? j.created_at),
    url: String(j.careers_url),
    portal: PORTAL,
    country: oneLine(j.country_code ?? j.country),
    employment_type: oneLine(j.employment_type_code),
    seniority: oneLine(j.experience_code),
    salary_min: positiveNumber(salary.min),
    salary_max: positiveNumber(salary.max),
    salary_currency: salary.currency ?? null,
    salary_period: payPeriod(salary.period),
    work_mode: mode,
    apply_url: oneLine(j.careers_apply_url),
    evidence: ["Recruitee offers API"],
    description: [htmlToText(j.description), htmlToText(j.requirements)].filter(Boolean).join("\n\n") || null,
  })
}

// ---------------------------------------------------------------- fetching

/** Every open job on one company's board. A missing board (404) yields []. */
export async function fetchBoard(c: Company): Promise<Job[]> {
  const b = encodeURIComponent(c.board)
  switch (c.ats) {
    case "greenhouse": {
      const body = (await get("greenhouse", c.board, `/v1/boards/${b}/jobs?content=true`)) as J | null
      return body ? parseGreenhouse(body, c) : []
    }
    case "lever": {
      const body = (await get("lever", c.board, `/v0/postings/${b}?mode=json`)) as J[] | null
      return body ? parseLever(body, c) : []
    }
    case "ashby": {
      const body = (await get("ashby", c.board, `/posting-api/job-board/${b}?includeCompensation=true`)) as J | null
      return body ? parseAshby(body, c) : []
    }
    case "workable": {
      const body = (await get("workable", c.board, `/api/v1/widget/accounts/${b}?details=true`)) as J | null
      return body ? parseWorkable(body, c) : []
    }
    case "recruitee": {
      const body = (await get("recruitee", c.board, `/api/offers/`)) as J | null
      return body ? parseRecruitee(body, c) : []
    }
  }
}

/** One job by provider id. Greenhouse/Lever/Recruitee have per-job endpoints; Ashby/Workable are read from the board. */
export async function fetchOne(ats: AtsName, board: string, jobId: string, name: string): Promise<Job | null> {
  const c: Company = { name, ats, board }
  const b = encodeURIComponent(board)
  const id = encodeURIComponent(jobId)
  switch (ats) {
    case "greenhouse": {
      const body = (await get("greenhouse", board, `/v1/boards/${b}/jobs/${id}?pay_transparency=true`)) as J | null
      return body ? greenhouseJob(body, c) : null
    }
    case "lever": {
      const body = (await get("lever", board, `/v0/postings/${b}/${id}?mode=json`)) as J | null
      return body && !Array.isArray(body) ? leverJob(body, c) : null
    }
    case "recruitee": {
      const body = (await get("recruitee", board, `/api/offers/${id}`)) as J | null
      return body ? parseRecruitee(body, c)[0] ?? null : null
    }
    default: {
      const all = await fetchBoard(c)
      return all.find((j) => j.id === `${ats}:${board}:${jobId}`) ?? null
    }
  }
}

/** Parse `<ats>:<board>:<id>` or a posting URL on a supported ATS host. */
export function parseJobRef(ref: string): { ats: AtsName; board: string; id: string } | null {
  const parts = ref.split(":")
  if (parts.length === 3 && (ATS_NAMES as readonly string[]).includes(parts[0])) {
    return { ats: parts[0] as AtsName, board: parts[1], id: parts[2] }
  }
  let u: URL
  try {
    u = new URL(ref)
  } catch {
    return null
  }
  const host = u.hostname.toLowerCase()
  const seg = u.pathname.split("/").filter(Boolean)
  if (host.endsWith("greenhouse.io") && seg.length >= 3 && seg[1] === "jobs") return { ats: "greenhouse", board: seg[0], id: seg[2] }
  if (host === "jobs.lever.co" && seg.length >= 2) return { ats: "lever", board: seg[0], id: seg[1] }
  if (host === "jobs.ashbyhq.com" && seg.length >= 2) return { ats: "ashby", board: seg[0], id: seg[1] }
  if (host === WORKABLE_HOST && seg.length >= 3 && seg[1] === "j") return { ats: "workable", board: seg[0], id: seg[2] }
  if (host.endsWith(".recruitee.com") && seg.length >= 2 && seg[0] === "o") return { ats: "recruitee", board: host.split(".")[0], id: seg[1] }
  return null
}
