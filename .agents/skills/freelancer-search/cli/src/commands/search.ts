// Freelancer.com through its official REST API (developers.freelancer.com),
// authenticated with the user's own OAuth token. Freelancer.co.id and the
// other Freelancer country sites show the same projects, so this one skill
// covers them. No freelancer.com page is fetched.

import { CliError, baseFromEnv, getJson, htmlToText, oneLine, userAgent, type Opts } from "../helpers.ts"
import { bool, makeGig, num, windowGigs, type Gig, type GigSearchOutcome } from "../gig.ts"

export const PORTAL = "freelancer-search"
export const UA = userAgent(PORTAL)
export const TOKEN_ENV = "FREELANCER_OAUTH_TOKEN"
export const PROJECT_URL = "https://www.freelancer.com/projects/"

export function apiBase(): string {
  return baseFromEnv("FREELANCER_API_URL", "https://www.freelancer.com/api")
}

/** OAuth access token from the environment only; never a flag, never printed. */
export function freelancerToken(): string {
  const token = (process.env[TOKEN_ENV] ?? "").trim()
  if (!token) {
    throw new CliError(
      `${TOKEN_ENV} is not set. Create an app at accounts.freelancer.com/settings/develop and export its OAuth token; see SKILL.md Setup.`,
      "MISSING_CREDENTIALS",
    )
  }
  return token
}

export interface FlProject {
  id?: number
  title?: string
  seo_url?: string | null
  type?: string | null
  local?: boolean | null
  currency?: { code?: string | null } | null
  budget?: { minimum?: number | null; maximum?: number | null } | null
  bid_stats?: { bid_count?: number | null } | null
  time_submitted?: number | null
  owner_id?: number | null
  jobs?: Array<{ name?: string }> | null
  description?: string | null
  preview_description?: string | null
  hourly_project_info?: { duration_enum?: string | null; commitment?: { hours?: number | null; interval?: string | null } | null } | null
}

export interface FlUser {
  location?: { country?: { name?: string | null } | null } | null
  status?: { payment_verified?: boolean | null } | null
  employer_reputation?: { entire_history?: { overall?: number | null; complete?: number | null } | null } | null
}

interface FlAnswer<T> {
  status?: string
  message?: string
  result?: T
}

const DURATIONS: Record<string, string> = {
  week: "less than 1 week",
  month: "1 week to 1 month",
  three_months: "1 to 3 months",
  six_months: "3 to 6 months",
  over_six_months: "more than 6 months",
}

/** Map one project (and its owner, when the API returned one) to the gig record. */
export function parseProject(p: FlProject, owner: FlUser | null): Gig | null {
  if (!p.id || !p.title) return null
  const type = p.type === "hourly" ? "hourly" : p.type === "fixed" ? "fixed" : null
  const rep = owner?.employer_reputation?.entire_history
  const duration = p.hourly_project_info?.duration_enum
  return makeGig({
    platform: "Freelancer.com",
    gig_id: String(p.id),
    url: p.seo_url ? `${PROJECT_URL}${p.seo_url.replace(/^\/+/, "")}` : `${PROJECT_URL}${p.id}`,
    title: oneLine(p.title) ?? p.title,
    client_country: owner?.location?.country?.name ?? null,
    client_verified_payment: bool(owner?.status?.payment_verified),
    client_rating: num(rep?.overall),
    client_hires: num(rep?.complete),
    // Total spend is not in Freelancer's public user object.
    client_total_spent: null,
    budget_type: type,
    budget_min: num(p.budget?.minimum),
    budget_max: num(p.budget?.maximum),
    budget_currency: p.currency?.code ?? null,
    est_duration: duration && DURATIONS[duration] ? DURATIONS[duration] : null,
    skills: (p.jobs ?? []).map((j) => j.name ?? "").filter(Boolean),
    proposals_count: num(p.bid_stats?.bid_count),
    // Bids come from the monthly allowance; the API does not state a per-project cost.
    connects_or_bids_cost: null,
    posted_at: p.time_submitted ? new Date(p.time_submitted * 1000).toISOString().slice(0, 10) : null,
    apply_method: "platform_bid",
    source_type: "api",
    evidence: [`Freelancer.com API project ${p.id}`, ...(p.local ? ["onsite: Freelancer local project (work at the client's location)"] : [])],
    description: htmlToText(p.description ?? p.preview_description ?? null),
  })
}

async function call<T>(path: string, params: URLSearchParams): Promise<T | null> {
  const token = freelancerToken()
  const body = await getJson<FlAnswer<T>>(`${apiBase()}${path}?${params}`, {
    label: "Freelancer.com API",
    ua: UA,
    headers: { "freelancer-oauth-v1": token },
  })
  if (body === null) return null
  if (body.status && body.status !== "success") throw new CliError(`Freelancer.com API: ${body.message ?? body.status}`, "BAD_RESPONSE")
  return body.result ?? null
}

export const USER_FLAGS = ["user_details", "user_country_details", "user_status", "user_employer_reputation"]

export async function runSearch(opts: Opts): Promise<GigSearchOutcome> {
  const limit = Math.min((opts.limit as number | undefined) ?? 25, 100)
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  const params = new URLSearchParams({
    query: String(opts.query ?? "flutter"),
    limit: String(limit),
    offset: String((page - 1) * limit),
    full_description: "true",
    job_details: "true",
    sort_field: "time_updated",
  })
  for (const f of USER_FLAGS) params.set(f, "true")
  params.append("project_types[]", "fixed")
  params.append("project_types[]", "hourly")
  const result = await call<{ projects?: FlProject[]; users?: Record<string, FlUser>; total_count?: number }>("/projects/0.1/projects/active/", params)
  const users = result?.users ?? {}
  const gigs = (result?.projects ?? [])
    .map((p) => parseProject(p, p.owner_id !== undefined && p.owner_id !== null ? users[String(p.owner_id)] ?? null : null))
    .filter((g): g is Gig => g !== null)
  return { results: windowGigs(gigs, { ...opts, page: 1, limit }), total: result?.total_count ?? null }
}

/** Project id from an id or a freelancer.* project URL (the API resolves seo_url too). */
export async function fetchProject(ref: string): Promise<Gig | null> {
  const id = ref.match(/^\d+$/) ? ref : null
  const params = new URLSearchParams({ full_description: "true", job_details: "true" })
  let project: FlProject | null
  if (id) {
    project = await call<FlProject>(`/projects/0.1/projects/${id}/`, params)
  } else {
    const m = ref.match(/^https?:\/\/(?:[a-z0-9-]+\.)*freelancer\.[a-z.]+\/projects\/([^?#]+?)\/?(?:[?#]|$)/i)
    if (!m) throw new CliError(`${ref} is not a Freelancer project id or URL`, "INVALID_VALUE")
    params.append("seo_urls[]", m[1])
    const found = await call<{ projects?: FlProject[] }>("/projects/0.1/projects/", params)
    project = found?.projects?.[0] ?? null
  }
  if (!project) return null
  let owner: FlUser | null = null
  if (project.owner_id) {
    const up = new URLSearchParams({ country_details: "true", status: "true", employer_reputation: "true" })
    owner = await call<FlUser>(`/users/0.1/users/${project.owner_id}/`, up)
  }
  return parseProject(project, owner)
}
