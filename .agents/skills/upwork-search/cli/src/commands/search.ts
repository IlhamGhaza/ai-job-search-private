// Upwork: the official GraphQL API when the user holds an approved API key
// (UPWORK_ACCESS_TOKEN), else search-provider leads through Brave. Upwork's
// Terms forbid scraping: no upwork.com page is ever requested by this skill.

import { CliError, baseFromEnv, htmlToText, oneLine, userAgent, type Opts } from "../helpers.ts"
import { bool, discoverGigs, makeGig, num, postJson, windowGigs, type Gig, type GigSearchOutcome, type Platform } from "../gig.ts"

export const PORTAL = "upwork-search"
export const UA = userAgent(PORTAL)
export const TOKEN_ENV = "UPWORK_ACCESS_TOKEN"
export const JOB_URL = "https://www.upwork.com/jobs/"

export const PLATFORM: Platform = {
  portal: PORTAL,
  name: "Upwork",
  hosts: ["upwork.com"],
  path: "/freelance-jobs/apply",
  apply_method: "platform_proposal",
}

/** The GraphQL endpoint; UPWORK_GRAPHQL_URL points the offline tests at a mock. */
export function graphqlUrl(): string {
  return baseFromEnv("UPWORK_GRAPHQL_URL", "https://api.upwork.com/graphql")
}

/** OAuth 2.0 access token from the environment only; never a flag, never printed. */
export function upworkToken(): string | null {
  return (process.env[TOKEN_ENV] ?? "").trim() || null
}

// Field names follow Upwork's public GraphQL schema (developer docs,
// "marketplaceJobPostingsSearch"). Upwork evolves the schema: if a field is
// rejected, introspect with your token and adjust this query and parseNode.
const NODE_FIELDS = `
  id ciphertext title description createdDateTime
  duration durationLabel engagement experienceLevel totalApplicants
  amount { rawValue currency }
  hourlyBudgetMin { rawValue currency }
  hourlyBudgetMax { rawValue currency }
  skills { name prettyName }
  preferredFreelancerLocation
  client {
    location { country }
    totalHires totalReviews totalFeedback verificationStatus
    totalSpent { rawValue currency }
  }`

export const SEARCH_QUERY = `query gigs($filter: MarketplaceJobPostingsSearchFilter, $sort: [MarketplaceJobPostingSearchSortAttribute]) {
  marketplaceJobPostingsSearch(marketPlaceJobFilter: $filter, searchType: USER_JOBS_SEARCH, sortAttributes: $sort) {
    totalCount
    edges { node { ${NODE_FIELDS} } }
  }
}`

export const DETAIL_QUERY = `query gig($id: ID!) { marketplaceJobPosting(id: $id) { ${NODE_FIELDS} } }`

interface Money {
  rawValue?: string | number | null
  currency?: string | null
}

export interface UpworkNode {
  id?: string
  ciphertext?: string | null
  title?: string
  description?: string | null
  createdDateTime?: string | null
  duration?: string | null
  durationLabel?: string | null
  engagement?: string | null
  experienceLevel?: string | null
  totalApplicants?: number | null
  amount?: Money | null
  hourlyBudgetMin?: Money | null
  hourlyBudgetMax?: Money | null
  skills?: Array<{ name?: string; prettyName?: string }> | null
  preferredFreelancerLocation?: string[] | null
  client?: {
    location?: { country?: string | null } | null
    totalHires?: number | null
    totalReviews?: number | null
    totalFeedback?: number | null
    verificationStatus?: string | null
    totalSpent?: Money | null
  } | null
}

interface GraphQlAnswer<T> {
  data?: T
  errors?: Array<{ message?: string }>
}

function money(m: Money | null | undefined): number | null {
  return num(m?.rawValue)
}

/** Map one marketplaceJobPosting node to the gig record. Missing -> null. */
export function parseNode(n: UpworkNode): Gig | null {
  if (!n.id || !n.title) return null
  const hourly = money(n.hourlyBudgetMin) !== null || money(n.hourlyBudgetMax) !== null
  const fixed = money(n.amount)
  const cur = (hourly ? n.hourlyBudgetMin?.currency ?? n.hourlyBudgetMax?.currency : n.amount?.currency) ?? null
  const verified = n.client?.verificationStatus
  const locations = (n.preferredFreelancerLocation ?? []).filter(Boolean)
  return makeGig({
    platform: "Upwork",
    gig_id: n.id,
    url: n.ciphertext ? `${JOB_URL}${n.ciphertext}` : `${JOB_URL}~${n.id}`,
    title: oneLine(n.title) ?? n.title,
    client_country: n.client?.location?.country ?? null,
    client_verified_payment: verified ? /^verified$/i.test(verified) : null,
    client_rating: num(n.client?.totalFeedback),
    client_hires: num(n.client?.totalHires),
    client_total_spent: money(n.client?.totalSpent),
    budget_type: hourly ? "hourly" : fixed !== null ? "fixed" : null,
    budget_min: hourly ? money(n.hourlyBudgetMin) : fixed,
    budget_max: hourly ? money(n.hourlyBudgetMax) : fixed,
    budget_currency: cur,
    est_duration: n.durationLabel ?? n.duration ?? null,
    skills: (n.skills ?? []).map((s) => s.prettyName ?? s.name ?? "").filter(Boolean),
    proposals_count: num(n.totalApplicants),
    // Connects per proposal are not in the public schema: read them on the page before you spend any.
    connects_or_bids_cost: null,
    posted_at: n.createdDateTime ? n.createdDateTime.slice(0, 10) : null,
    apply_method: "platform_proposal",
    source_type: "api",
    freelancer_locations: locations.length ? locations : null,
    evidence: [`Upwork GraphQL API marketplaceJobPosting ${n.id}`, ...(n.experienceLevel ? [`experience level: ${n.experienceLevel}`] : [])],
    description: htmlToText(n.description ?? null),
  })
}

async function graphql<T>(query: string, variables: Record<string, unknown>, token: string): Promise<T> {
  const body = await postJson<GraphQlAnswer<T>>(graphqlUrl(), { query, variables }, {
    label: "Upwork GraphQL API",
    ua: UA,
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!body) throw new CliError("Upwork GraphQL API answered 404", "HTTP_ERROR")
  if (body.errors?.length) {
    const msg = body.errors.map((e) => e.message ?? "error").join("; ").slice(0, 300)
    throw new CliError(`Upwork GraphQL API: ${msg}`, /auth|scope|permission/i.test(msg) ? "UNAUTHORIZED" : "BAD_RESPONSE")
  }
  if (!body.data) throw new CliError("Upwork GraphQL API returned no data", "BAD_RESPONSE")
  return body.data
}

export async function runSearch(opts: Opts): Promise<GigSearchOutcome> {
  const query = String(opts.query ?? "flutter")
  const token = upworkToken()
  if (!token) {
    // No approved key: search-provider leads only (MISSING_CREDENTIALS if the Brave key is absent too).
    const { results, warnings } = await discoverGigs(PLATFORM, { ...opts, query }, UA)
    return {
      results: windowGigs(results, { ...opts, page: 1 }),
      total: null,
      warnings: [`${TOKEN_ENV} not set: Upwork results are search-engine leads only (see SKILL.md to apply for API access)`, ...warnings],
    }
  }
  const limit = Math.min((opts.limit as number | undefined) ?? 25, 50)
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  const data = await graphql<{ marketplaceJobPostingsSearch?: { totalCount?: number; edges?: Array<{ node?: UpworkNode }> } }>(
    SEARCH_QUERY,
    {
      filter: { searchExpression_eq: query, pagination_eq: { after: String((page - 1) * limit), first: limit } },
      sort: [{ field: "RECENCY" }],
    },
    token,
  )
  const nodes = data.marketplaceJobPostingsSearch?.edges ?? []
  const results = nodes.map((e) => (e.node ? parseNode(e.node) : null)).filter((g): g is Gig => g !== null)
  return { results: windowGigs(results, { ...opts, page: 1, limit }), total: data.marketplaceJobPostingsSearch?.totalCount ?? null }
}
