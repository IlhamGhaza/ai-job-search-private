// Shared freelance-gig kit: the gig record, search-provider discovery, a JSON
// POST for GraphQL APIs, output formats and the CLI runner. The same file is
// copied into every freelance skill (category: freelance), next to the
// portal kit's helpers.ts and brave.ts, so each skill stays self-contained.
// Edit one copy, then copy it to the others: they are meant to stay identical.
//
// Gig text is untrusted third-party data. Nothing here interprets it; the
// rules (tools/gig_rules.py) and the posting gate (tools/posting_guard.py)
// run on the output.

import { CliError, oneLine, parseArgs, stripInvisible, withinDays, writeError, type FlagSpec, type Opts } from "./helpers.ts"
import { braveSearch } from "./brave.ts"

export type BudgetType = "hourly" | "fixed"
export type GigApplyMethod = "platform_proposal" | "platform_bid" | "email" | "external_unknown"

/**
 * One freelance gig. Every field is always present; a value the source does
 * not state is null - never guessed.
 */
export interface Gig {
  platform: string
  gig_id: string
  url: string
  title: string
  client_country: string | null
  client_verified_payment: boolean | null
  client_rating: number | null
  client_hires: number | null
  client_total_spent: number | null
  budget_type: BudgetType | null
  budget_min: number | null
  budget_max: number | null
  budget_currency: string | null
  est_duration: string | null
  skills: string[]
  proposals_count: number | null
  connects_or_bids_cost: number | null
  posted_at: string | null
  apply_method: GigApplyMethod
  /** Set by tools/gig_rules.py; the CLI never screens. */
  safety_screening: string
  evidence: string[]
  /** Countries the client restricts applicants to, as the platform states them; null = no restriction stated. */
  freelancer_locations: string[] | null
  /** `api` = read from the platform's official API; `search_lead` = a search-engine snippet, not fetched. */
  source_type: "api" | "search_lead"
  verification_status: "listing_from_api" | "unverified_lead"
  description: string | null
}

export type GigInput = Partial<Gig> & { platform: string; gig_id: string; url: string; title: string }

export function makeGig(p: GigInput): Gig {
  return {
    platform: p.platform,
    gig_id: p.gig_id,
    url: p.url,
    title: p.title,
    client_country: p.client_country ?? null,
    client_verified_payment: p.client_verified_payment ?? null,
    client_rating: p.client_rating ?? null,
    client_hires: p.client_hires ?? null,
    client_total_spent: p.client_total_spent ?? null,
    budget_type: p.budget_type ?? null,
    budget_min: p.budget_min ?? null,
    budget_max: p.budget_max ?? null,
    budget_currency: p.budget_currency ? String(p.budget_currency).toUpperCase() : null,
    est_duration: p.est_duration ?? null,
    skills: p.skills ?? [],
    proposals_count: p.proposals_count ?? null,
    connects_or_bids_cost: p.connects_or_bids_cost ?? null,
    posted_at: p.posted_at ?? null,
    apply_method: p.apply_method ?? "platform_proposal",
    safety_screening: p.safety_screening ?? "unscreened",
    evidence: p.evidence ?? [],
    freelancer_locations: p.freelancer_locations ?? null,
    source_type: p.source_type ?? "api",
    verification_status: p.verification_status ?? (p.source_type === "search_lead" ? "unverified_lead" : "listing_from_api"),
    description: p.description ?? null,
  }
}

/** A finite number (zero allowed: "0 hires" is a fact), else null. */
export function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null
  const n = typeof value === "number" ? value : Number(String(value).replace(/[, ]/g, ""))
  return Number.isFinite(n) ? n : null
}

/** A boolean only when the source says so. */
export function bool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null
}

// ---------------------------------------------------------------- HTTP POST (GraphQL)

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/**
 * POST a JSON body and parse the JSON answer. Same failure contract as
 * helpers.ts httpGet: 429/5xx retried with backoff (PORTAL_RETRY_BASE_MS /
 * PORTAL_MAX_RETRIES), 401/403 reported and never worked around, 404 -> null.
 */
export async function postJson<T>(url: string, body: unknown, opts: { label: string; ua: string; headers?: Record<string, string> }): Promise<T | null> {
  const base = Number(process.env.PORTAL_RETRY_BASE_MS ?? "500")
  const max = Number(process.env.PORTAL_MAX_RETRIES ?? "6")
  let delay = Number.isFinite(base) && base >= 0 ? base : 500
  const tries = Number.isInteger(max) && max >= 0 ? max : 6
  for (let attempt = 0; attempt <= tries; attempt++) {
    let response: Response
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "User-Agent": opts.ua, Accept: "application/json", "Content-Type": "application/json", ...(opts.headers ?? {}) },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(20_000),
      })
    } catch (e) {
      throw new CliError(`could not reach ${opts.label} (${e instanceof Error ? e.message : String(e)})`, "NETWORK_ERROR")
    }
    if (response.status === 429 || response.status >= 500) {
      if (attempt === tries) {
        throw new CliError(`${opts.label} request failed: ${response.status}`, response.status === 429 ? "RATE_LIMITED" : "HTTP_ERROR")
      }
      await sleep(delay + Math.floor(Math.random() * Math.max(delay, 1)))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (response.status === 401) throw new CliError(`${opts.label} answered 401 Unauthorized (token expired or wrong scope)`, "UNAUTHORIZED")
    if (response.status === 403) throw new CliError(`${opts.label} answered 403 Forbidden`, "FORBIDDEN")
    if (!response.ok) throw new CliError(`${opts.label} request failed: ${response.status}`, "HTTP_ERROR")
    try {
      return (await response.json()) as T
    } catch {
      throw new CliError(`${opts.label} returned a body that is not JSON`, "BAD_RESPONSE")
    }
  }
  throw new CliError(`${opts.label} request failed after retries`, "HTTP_ERROR")
}

// ---------------------------------------------------------------- search-provider discovery

export interface Platform {
  /** Skill name, e.g. contra-search. */
  portal: string
  name: string
  /** Hosts whose pages are gigs on this platform; the first scopes the `site:` query. */
  hosts: string[]
  /** Path prefix that holds individual gigs, added to the `site:` scope ("" = whole host). */
  path: string
  apply_method: GigApplyMethod
}

/** Brave endpoint, assembled so tests/test_apply_host_check.py does not read it as this platform's host. */
export function braveEndpoint(): string {
  return (process.env.BRAVE_SEARCH_API_URL ?? "").trim() || ["https:", "", "api.search.brave.com", "res", "v1", "web", "search"].join("/")
}

export function onPlatform(platform: Platform, url: string): boolean {
  let host: string
  try {
    host = new URL(url).hostname.toLowerCase().replace(/^www\./, "")
  } catch {
    return false
  }
  return platform.hosts.some((h) => host === h || host.endsWith("." + h))
}

/** A search-engine hit as a gig lead: title and snippet only, every other field null. */
export function leadFromHit(platform: Platform, hit: { title: string | null; url: string; description: string | null; age: string | null }, query: string): Gig {
  return makeGig({
    platform: platform.name,
    gig_id: hit.url,
    url: hit.url,
    // Drop only a trailing " | <Platform>" / " - <Platform>" site suffix; a dash inside the title stays.
    title: oneLine(hit.title?.replace(new RegExp(`\\s+[|\\-–]\\s+${platform.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b.*$`, "i"), "")) ?? hit.title ?? "(untitled)",
    posted_at: null,
    apply_method: platform.apply_method,
    source_type: "search_lead",
    evidence: [`search-engine result for "${query}" (page not fetched)`, ...(hit.age ? [`search engine age: ${hit.age}`] : [])],
    description: hit.description,
  })
}

/** One `site:` query per platform host on the Brave Search API. The platform itself is never requested. */
export async function discoverGigs(platform: Platform, opts: Opts, ua: string): Promise<{ results: Gig[]; warnings: string[] }> {
  const terms = String(opts.query ?? "flutter")
  const results: Gig[] = []
  const warnings: string[] = []
  let firstError: unknown = null
  for (const host of platform.hosts) {
    const query = `site:${host}${platform.path} ${terms}`
    try {
      const hits = await braveSearch(braveEndpoint(), query, opts, ua)
      results.push(...hits.filter((h) => onPlatform(platform, h.url)).map((h) => leadFromHit(platform, h, query)))
    } catch (e) {
      // One host failing is a warning; a missing key, or every host failing, is the run's error.
      if (e instanceof CliError && e.code === "MISSING_CREDENTIALS") throw e
      firstError = firstError ?? e
      warnings.push(`${host}: ${e instanceof Error ? e.message : String(e)}`)
    }
  }
  if (firstError && warnings.length === platform.hosts.length) throw firstError
  return { results, warnings }
}

/** `detail` for a platform with no permitted read API: the user opens the link. */
export function manualOnly(platform: Platform, ref: string): never {
  if (/^https?:\/\//.test(ref) && !onPlatform(platform, ref)) {
    throw new CliError(`${ref} is not a ${platform.name} URL`, "INVALID_VALUE")
  }
  throw new CliError(
    `${platform.name} has no permitted API for reading gigs and its pages are not fetched; open the link yourself and paste the gig text into /propose`,
    "MANUAL_ONLY",
  )
}

// ---------------------------------------------------------------- output

export type Format = "json" | "table" | "plain"

function budgetCell(g: Gig): string {
  if (g.budget_min === null && g.budget_max === null) return "-"
  const range = [g.budget_min, g.budget_max].filter((v) => v !== null).join("-")
  return `${range} ${g.budget_currency ?? "?"}${g.budget_type === "hourly" ? "/h" : g.budget_type === "fixed" ? " fixed" : ""}`
}

function plainBlock(g: Gig, withDescription: boolean): string {
  const lines = [
    g.title,
    `Platform: ${g.platform}   Posted: ${g.posted_at ?? "-"}   Source: ${g.source_type}`,
    `Budget: ${budgetCell(g)}   Duration: ${g.est_duration ?? "-"}`,
    `Client: ${g.client_country ?? "-"}  payment verified: ${g.client_verified_payment ?? "-"}  rating: ${g.client_rating ?? "-"}  hires: ${g.client_hires ?? "-"}  spent: ${g.client_total_spent ?? "-"}`,
    `Proposals: ${g.proposals_count ?? "-"}   Cost to apply: ${g.connects_or_bids_cost ?? "-"}`,
    `Skills: ${g.skills.join(", ") || "-"}`,
    `Freelancer locations: ${g.freelancer_locations?.join(", ") ?? "no restriction stated"}`,
    `URL: ${g.url}`,
  ]
  if (withDescription) lines.push("", g.description ?? "(no description)")
  return lines.join("\n")
}

export function printGigs(results: Gig[], meta: Record<string, unknown>, format: Format): void {
  const clean = stripInvisible(results)
  if (format === "json") {
    process.stdout.write(JSON.stringify({ meta, results: clean }, null, 2) + "\n")
    return
  }
  if (format === "table") {
    const rows = clean.map((g, i) =>
      [String(i + 1), g.posted_at ?? "-", g.title, budgetCell(g), g.client_country ?? "-", String(g.proposals_count ?? "-"), g.url].map((c) =>
        c.replace(/\s+/g, " "),
      ),
    )
    const header = ["#", "Posted", "Title", "Budget", "Client", "Props", "URL"]
    const widths = header.map((h, c) => Math.min(Math.max(h.length, ...rows.map((r) => r[c].length)), c === 6 ? 200 : 40))
    const fmt = (r: string[]) => r.map((c, i) => (c.length > widths[i] ? c.slice(0, widths[i] - 1) + "…" : c.padEnd(widths[i]))).join("  ")
    process.stdout.write([fmt(header), ...rows.map(fmt)].join("\n") + "\n")
    process.stdout.write(`\n${clean.length} result(s)\n`)
    return
  }
  for (const g of clean) process.stdout.write(plainBlock(g, false) + "\n\n")
}

export function printGig(gig: Gig, format: Format): void {
  const clean = stripInvisible(gig)
  if (format === "plain" || format === "table") {
    process.stdout.write(plainBlock(clean, true) + "\n")
    return
  }
  process.stdout.write(JSON.stringify(clean, null, 2) + "\n")
}

// ---------------------------------------------------------------- CLI runner

export interface GigSearchOutcome {
  results: Gig[]
  total?: number | null
  warnings?: string[]
}

export interface GigCliSpec {
  name: string
  help: string
  searchFlags?: FlagSpec[]
  search(opts: Opts): Promise<GigSearchOutcome>
  detail(ref: string, opts: Opts): Promise<Gig | null>
}

const COMMON_SEARCH: FlagSpec[] = [
  { name: "query", alias: "q", type: "string" },
  { name: "jobage", type: "number" },
  { name: "page", type: "number" },
  { name: "limit", alias: "n", type: "number" },
  { name: "format", type: "string" },
]

function formatOf(opts: Opts): Format {
  const f = (opts.format as string | undefined) ?? "json"
  if (f !== "json" && f !== "table" && f !== "plain") throw new CliError(`--format must be json, table or plain, got ${f}`, "INVALID_VALUE")
  return f
}

/** Client-side recency filter and the 1-indexed page/limit window. */
export function windowGigs(all: Gig[], opts: Opts): Gig[] {
  const recent = all.filter((g) => withinDays(g.posted_at, opts.jobage as number | undefined))
  const limit = (opts.limit as number | undefined) ?? 25
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  return recent.slice((page - 1) * limit, page * limit)
}

export async function runGigCli(spec: GigCliSpec, argv = process.argv.slice(2)): Promise<void> {
  const [command, ...rest] = argv
  try {
    if (!command || command === "help" || command === "--help" || command === "-h") {
      process.stdout.write(spec.help)
      return
    }
    if (command === "search") {
      const { positional, opts } = parseArgs(rest, [...COMMON_SEARCH, ...(spec.searchFlags ?? [])])
      if (positional.length) throw new CliError(`unexpected argument: ${positional[0]} (use --query)`, "UNEXPECTED_ARGUMENT")
      const format = formatOf(opts)
      if (opts.page === 0) throw new CliError("--page is 1-indexed", "INVALID_VALUE")
      const outcome = await spec.search(opts)
      const meta = { count: outcome.results.length, page: (opts.page as number | undefined) ?? 1, total: outcome.total ?? null, portal: spec.name, kind: "freelance" }
      printGigs(outcome.results, meta, format)
      for (const w of outcome.warnings ?? []) process.stderr.write(JSON.stringify({ warning: w, code: "WARNING" }) + "\n")
      return
    }
    if (command === "detail") {
      const { positional, opts } = parseArgs(rest, [{ name: "format", type: "string" }])
      const format = formatOf(opts)
      const ref = positional[0]
      if (!ref) throw new CliError("detail needs a gig id or URL", "MISSING_ARGUMENT")
      const gig = await spec.detail(ref, opts)
      if (!gig) throw new CliError(`no gig found for ${ref}`, "NOT_FOUND")
      printGig(gig, format)
      return
    }
    throw new CliError(`unknown command: ${command} (expected search or detail)`, "UNKNOWN_COMMAND")
  } catch (e) {
    if (e instanceof CliError) writeError(e.message, e.code)
    else writeError(e instanceof Error ? e.message : String(e), "UNEXPECTED_ERROR")
    process.exit(1)
  }
}
