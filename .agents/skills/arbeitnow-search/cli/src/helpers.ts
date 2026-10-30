// Shared portal-CLI plumbing: HTTP with backoff, text hygiene, the contract
// result shape, output formats and argument parsing. The same file is copied
// into every portal skill added for the global Flutter search, so each skill
// stays self-contained (zero runtime dependencies, runs with plain `bun`).
// Edit one copy, then copy it to the others: they are meant to stay identical.

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

/** An error the CLI reports as `{error, code}` on stderr with exit 1. */
export class CliError extends Error {
  code: string
  constructor(message: string, code: string) {
    super(message)
    this.code = code
  }
}

export function userAgent(portal: string): string {
  return `Mozilla/5.0 (compatible; ${portal}-cli/1.0)`
}

// ---------------------------------------------------------------- HTTP

// The most httpGet sleeps across all retries of one request, so an outage
// degrades this source quickly instead of outlasting the caller's timeout.
const RETRY_BUDGET_MS = 30_000

/** Retry knobs. PORTAL_RETRY_BASE_MS / PORTAL_MAX_RETRIES exist for the offline tests. */
function retryConfig(): { base: number; max: number } {
  const base = Number(process.env.PORTAL_RETRY_BASE_MS ?? "500")
  const max = Number(process.env.PORTAL_MAX_RETRIES ?? "6")
  return {
    base: Number.isFinite(base) && base >= 0 ? base : 500,
    max: Number.isInteger(max) && max >= 0 ? max : 6,
  }
}

/** The wait a 429/503 asks for via `Retry-After`, in ms, or null. */
export function retryAfterMs(header: string | null, now = Date.now()): number | null {
  if (!header) return null
  const value = header.trim()
  if (/^\d+$/.test(value)) return Number(value) * 1000
  const date = Date.parse(value)
  if (Number.isNaN(date)) return null
  return Math.max(date - now, 0)
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

export interface GetOptions {
  /** Human name of the service, used in error messages. */
  label: string
  ua: string
  accept?: string
  headers?: Record<string, string>
  timeoutMs?: number
}

/**
 * GET a URL. Retries 429/5xx with exponential backoff and jitter (honouring
 * Retry-After within RETRY_BUDGET_MS); returns null on 404; fails fast on a
 * connection error. 401/403 are reported as UNAUTHORIZED/FORBIDDEN, never
 * retried and never worked around.
 */
export async function httpGet(url: string, opts: GetOptions): Promise<string | null> {
  const { base, max } = retryConfig()
  let delay = base
  let waited = 0
  for (let attempt = 0; attempt <= max; attempt++) {
    let response: Response
    try {
      response = await fetch(url, {
        headers: { "User-Agent": opts.ua, Accept: opts.accept ?? "application/json", ...(opts.headers ?? {}) },
        redirect: "follow",
        signal: AbortSignal.timeout(opts.timeoutMs ?? 20_000),
      })
    } catch (e) {
      throw new CliError(
        `could not reach ${opts.label} (${e instanceof Error ? e.message : String(e)})`,
        "NETWORK_ERROR",
      )
    }
    if (response.status === 429 || response.status >= 500) {
      const code = response.status === 429 ? "RATE_LIMITED" : "HTTP_ERROR"
      if (attempt === max) {
        throw new CliError(`${opts.label} request failed: ${response.status} ${response.statusText}`.trim(), code)
      }
      const backoff = delay + Math.floor(Math.random() * Math.max(delay, 1))
      const wait = Math.max(backoff, retryAfterMs(response.headers.get("Retry-After")) ?? 0)
      if (waited + wait > RETRY_BUDGET_MS) {
        throw new CliError(
          `${opts.label} request failed: ${response.status}; retry would exceed the ${RETRY_BUDGET_MS / 1000}s budget`,
          code,
        )
      }
      await sleep(wait)
      waited += wait
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (response.status === 401) throw new CliError(`${opts.label} answered 401 Unauthorized`, "UNAUTHORIZED")
    if (response.status === 403) throw new CliError(`${opts.label} answered 403 Forbidden`, "FORBIDDEN")
    if (!response.ok) {
      throw new CliError(`${opts.label} request failed: ${response.status} ${response.statusText}`.trim(), "HTTP_ERROR")
    }
    return await response.text()
  }
  throw new CliError(`${opts.label} request failed after retries`, "HTTP_ERROR")
}

/** GET and parse JSON; null on 404. */
export async function getJson<T>(url: string, opts: GetOptions): Promise<T | null> {
  const text = await httpGet(url, opts)
  if (text === null) return null
  try {
    return JSON.parse(text) as T
  } catch {
    throw new CliError(`${opts.label} returned a body that is not JSON`, "BAD_RESPONSE")
  }
}

/** An env-var base URL override (for self-hosting and the offline tests), else the default. */
export function baseFromEnv(envVar: string, fallback: string): string {
  const raw = (process.env[envVar] ?? "").trim()
  return (raw || fallback).replace(/\/+$/, "")
}

// ---------------------------------------------------------------- text hygiene

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

export function decodeEntities(text: string): string {
  return text
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
}

/**
 * Characters a reader never sees but a model does: C0/C1 controls (except tab,
 * newline, CR), soft hyphen, bidi controls, zero-width characters, BOM,
 * variation selectors and Unicode tag characters. Listing text is third-party
 * data; these can carry hidden instructions.
 */
const INVISIBLE_CHARS =
  /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F­؜᠎​-‏‪-‮⁠-⁯︀-️﻿\u{E0000}-\u{E007F}\u{E0100}-\u{E01EF}]/gu

/** Strip INVISIBLE_CHARS from every string in a value, recursively: the output boundary. */
export function stripInvisible<T>(value: T): T {
  if (typeof value === "string") return value.replace(INVISIBLE_CHARS, "") as T
  if (Array.isArray(value)) return value.map(stripInvisible) as T
  if (value !== null && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, stripInvisible(v)])) as T
  }
  return value
}

const VOID_TAGS = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"])

function isHiddenTag(attrs: string): boolean {
  for (const m of attrs.matchAll(/([^\s"'=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g)) {
    const name = m[1].toLowerCase()
    const value = m[2] ?? m[3] ?? m[4] ?? ""
    if (name === "hidden" || (name === "aria-hidden" && value.toLowerCase() === "true")) return true
    if (name === "style" && /(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all)\b/i.test(value)) {
      return true
    }
  }
  return false
}

/**
 * Drop markup a browser never renders - comments, <script>/<style>/<template>
 * blocks, elements marked hidden - before tags are stripped. Same algorithm as
 * linkedin-search's visibleHtml.
 */
export function visibleHtml(html: string): string {
  const src = html
    .replace(/<!--[\s\S]*?(?:-->|$)/g, "")
    .replace(/<(script|style|template|noscript)\b[^>]*>[\s\S]*?(?:<\/\1\s*>|$)/gi, "")
  const open = /<([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?>/g
  const kept: string[] = []
  let from = 0
  let m: RegExpExecArray | null
  while ((m = open.exec(src)) !== null) {
    if (!m[2] || !isHiddenTag(m[2])) continue
    const tag = m[1].toLowerCase()
    let end = open.lastIndex
    if (!VOID_TAGS.has(tag) && !m[0].endsWith("/>")) {
      const same = new RegExp(`<(/?)${tag}\\b[^>]*>`, "gi")
      same.lastIndex = end
      end = src.length
      let depth = 1
      let s: RegExpExecArray | null
      while ((s = same.exec(src)) !== null) {
        if (s[1]) depth--
        else if (!s[0].endsWith("/>")) depth++
        if (depth === 0) {
          end = same.lastIndex
          break
        }
      }
    }
    kept.push(src.slice(from, m.index))
    from = end
    open.lastIndex = end
  }
  kept.push(src.slice(from))
  return kept.join("")
}

/** HTML (possibly entity-escaped once, as some APIs ship it) to readable text with paragraph breaks. */
export function htmlToText(html: string | null | undefined): string | null {
  if (html === null || html === undefined) return null
  let src = String(html)
  // Some APIs (Greenhouse, Arbeitnow) escape the markup itself: &lt;p&gt;.
  if (!/<[a-zA-Z/]/.test(src) && /&lt;[a-zA-Z/]/.test(src)) src = decodeEntities(src)
  const text = visibleHtml(src)
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\s*li\b[^>]*>/gi, "\n- ")
    .replace(/<\/\s*(p|div|h[1-6]|ul|ol|li|tr|section|article)\s*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
  const decoded = decodeEntities(text)
    .replace(/[ \t\f\v]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
  return decoded || null
}

/** One-line text for a short field (title, company, location); null when empty. */
export function oneLine(value: unknown): string | null {
  if (value === null || value === undefined) return null
  const text = htmlToText(String(value))
  if (!text) return null
  return text.replace(/\s+/g, " ").trim() || null
}

// ---------------------------------------------------------------- dates & numbers

/** A contract date (YYYY-MM-DD) from an ISO string, an RFC 2822 date, or epoch seconds/ms. */
export function contractDate(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null
  let ms: number
  if (typeof value === "number" || (typeof value === "string" && /^\d{9,13}$/.test(value.trim()))) {
    const n = Number(value)
    ms = n > 1e12 ? n : n * 1000
  } else if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value.trim())) {
    return value.trim().slice(0, 10)
  } else {
    ms = Date.parse(String(value))
  }
  if (!Number.isFinite(ms)) return null
  return new Date(ms).toISOString().slice(0, 10)
}

/** Whether a contract date is within the last `days` days. Unknown dates pass (flagged downstream). */
export function withinDays(date: string | null, days: number | undefined, now = Date.now()): boolean {
  if (!days || !date) return true
  const ms = Date.parse(date + "T00:00:00Z")
  if (Number.isNaN(ms)) return true
  return now - ms <= days * 86_400_000 + 86_400_000
}

/** A positive finite number, else null. Zero means "not stated" in most job APIs. */
export function positiveNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null
  const n = typeof value === "number" ? value : Number(String(value).replace(/[, ]/g, ""))
  return Number.isFinite(n) && n > 0 ? n : null
}

/** Normalise a pay period word to year|month|week|day|hour, else null. */
export function payPeriod(value: unknown): string | null {
  if (!value) return null
  const v = String(value).toLowerCase()
  if (/year|annual|annum|yearly|^y$|1 year/.test(v)) return "year"
  if (/month|monthly|^m$|1 month/.test(v)) return "month"
  if (/week/.test(v)) return "week"
  if (/day|daily/.test(v)) return "day"
  if (/hour/.test(v)) return "hour"
  return null
}

// ---------------------------------------------------------------- query matching

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Client-side keyword matcher for sources that have no server-side search.
 * `a b` = all terms, `"a b"` = phrase, uppercase `OR` separates alternatives.
 * Terms match on word boundaries, case-insensitively, unless `substring` is
 * set (compounding languages: "utvikler" inside "Systemutvikler"). Empty query
 * matches all.
 */
export function queryMatcher(query: string | undefined, substring = false): (text: string) => boolean {
  const q = (query ?? "").trim()
  if (!q) return () => true
  const alternatives = q.split(/\s+OR\s+/).map((alt) => {
    const terms: string[] = []
    alt.replace(/"([^"]+)"|(\S+)/g, (_, phrase, word) => {
      terms.push((phrase ?? word).toLowerCase())
      return ""
    })
    if (substring) return terms.map((t) => new RegExp(escapeRegex(t), "iu"))
    return terms.map((t) => new RegExp(`(^|[^\\p{L}\\p{N}])${escapeRegex(t)}($|[^\\p{L}\\p{N}])`, "iu"))
  })
  return (text: string) => alternatives.some((terms) => terms.every((re) => re.test(text)))
}

// ---------------------------------------------------------------- the job record

export type SourceType = "listing" | "social_post"

/**
 * The portal contract's result shape plus the optional fields the global
 * search pipeline reads (tools/job_rules.py). Every field is always present;
 * a value the source does not state is null - never guessed.
 */
export interface Job {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  portal: string
  source_type: SourceType
  country: string | null
  employment_type: string | null
  seniority: string | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  salary_period: string | null
  salary_gross_or_net: string | null
  salary_text: string | null
  remote_eligibility: string | null
  work_mode: string | null
  visa_sponsorship: string | null
  relocation: string | null
  required_experience: string | null
  deadline: string | null
  apply_url: string | null
  verification_status: string
  evidence: string[]
  description: string | null
}

export type JobInput = Partial<Job> & { id: string; title: string; url: string; portal: string }

export function makeJob(p: JobInput): Job {
  return {
    id: p.id,
    title: p.title,
    company: p.company ?? null,
    location: p.location ?? null,
    date: p.date ?? null,
    url: p.url,
    portal: p.portal,
    source_type: p.source_type ?? "listing",
    country: p.country ?? null,
    employment_type: p.employment_type ?? null,
    seniority: p.seniority ?? null,
    salary_min: p.salary_min ?? null,
    salary_max: p.salary_max ?? null,
    salary_currency: p.salary_currency ? String(p.salary_currency).toUpperCase() : null,
    salary_period: p.salary_period ?? null,
    salary_gross_or_net: p.salary_gross_or_net ?? null,
    salary_text: p.salary_text ?? null,
    remote_eligibility: p.remote_eligibility ?? null,
    work_mode: p.work_mode ?? null,
    visa_sponsorship: p.visa_sponsorship ?? null,
    relocation: p.relocation ?? null,
    required_experience: p.required_experience ?? null,
    deadline: p.deadline ?? null,
    apply_url: p.apply_url ?? null,
    verification_status: p.verification_status ?? "listing_from_portal",
    evidence: p.evidence ?? [],
    description: p.description ?? null,
  }
}

// ---------------------------------------------------------------- output

export type Format = "json" | "table" | "plain"

function salaryCell(j: Job): string {
  if (j.salary_min === null && j.salary_max === null) return j.salary_text ? j.salary_text.slice(0, 24) : "-"
  const range = [j.salary_min, j.salary_max].filter((v) => v !== null).join("-")
  return `${range} ${j.salary_currency ?? "?"}/${j.salary_period ?? "?"}`
}

export function printSearch(results: Job[], meta: Record<string, unknown>, format: Format): void {
  const clean = stripInvisible(results)
  if (format === "json") {
    process.stdout.write(JSON.stringify({ meta, results: clean }, null, 2) + "\n")
    return
  }
  if (format === "table") {
    const rows = clean.map((j, i) =>
      [String(i + 1), j.date ?? "-", j.title, j.company ?? "-", j.location ?? "-", salaryCell(j), j.url].map((c) =>
        c.replace(/\s+/g, " "),
      ),
    )
    const header = ["#", "Date", "Title", "Company", "Location", "Salary", "URL"]
    const widths = header.map((h, c) => Math.min(Math.max(h.length, ...rows.map((r) => r[c].length)), c === 6 ? 200 : 40))
    const fmt = (r: string[]) => r.map((c, i) => (c.length > widths[i] ? c.slice(0, widths[i] - 1) + "…" : c.padEnd(widths[i]))).join("  ")
    process.stdout.write([fmt(header), ...rows.map(fmt)].join("\n") + "\n")
    process.stdout.write(`\n${clean.length} result(s)\n`)
    return
  }
  for (const j of clean) process.stdout.write(plainBlock(j, false) + "\n\n")
}

function plainBlock(j: Job, withDescription: boolean): string {
  const lines = [
    `${j.title}`,
    `Company: ${j.company ?? "-"}`,
    `Location: ${j.location ?? "-"}${j.country ? ` (${j.country})` : ""}`,
    `Posted: ${j.date ?? "-"}   Deadline: ${j.deadline ?? "-"}`,
    `Type: ${j.employment_type ?? "-"}   Seniority: ${j.seniority ?? "-"}   Work mode: ${j.work_mode ?? "-"}`,
    `Salary: ${salaryCell(j)}`,
    `Remote eligibility: ${j.remote_eligibility ?? "-"}`,
    `Visa sponsorship: ${j.visa_sponsorship ?? "-"}`,
    `URL: ${j.url}`,
  ]
  if (j.apply_url && j.apply_url !== j.url) lines.push(`Apply: ${j.apply_url}`)
  if (j.verification_status !== "listing_from_portal") lines.push(`Verification: ${j.verification_status}`)
  if (withDescription) lines.push("", j.description ?? "(no description)")
  return lines.join("\n")
}

export function printDetail(job: Job, format: Format): void {
  const clean = stripInvisible(job)
  if (format === "plain" || format === "table") {
    process.stdout.write(plainBlock(clean, true) + "\n")
    return
  }
  process.stdout.write(JSON.stringify(clean, null, 2) + "\n")
}

// ---------------------------------------------------------------- CLI runner

export interface FlagSpec {
  name: string
  alias?: string
  type: "string" | "number" | "boolean"
}

export type Opts = Record<string, string | number | boolean | undefined>

export interface SearchOutcome {
  results: Job[]
  total?: number | null
  warnings?: string[]
}

export interface CliSpec {
  name: string
  help: string
  /** Portal-specific search flags; query/jobage/page/limit/format are built in. */
  searchFlags?: FlagSpec[]
  detailFlags?: FlagSpec[]
  search(opts: Opts): Promise<SearchOutcome>
  detail(id: string, opts: Opts): Promise<Job | null>
}

const COMMON_SEARCH: FlagSpec[] = [
  { name: "query", alias: "q", type: "string" },
  { name: "jobage", type: "number" },
  { name: "page", type: "number" },
  { name: "limit", alias: "n", type: "number" },
  { name: "format", type: "string" },
]
const COMMON_DETAIL: FlagSpec[] = [{ name: "format", type: "string" }]

export function parseArgs(argv: string[], specs: FlagSpec[]): { positional: string[]; opts: Opts } {
  const byName = new Map<string, FlagSpec>()
  for (const s of specs) {
    byName.set(s.name, s)
    if (s.alias) byName.set(s.alias, s)
  }
  const positional: string[] = []
  const opts: Opts = {}
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (!arg.startsWith("-") || arg === "-") {
      positional.push(arg)
      continue
    }
    const [rawName, inline] = arg.replace(/^-+/, "").split(/=(.*)/s, 2)
    const spec = byName.get(rawName)
    if (!spec) throw new CliError(`unknown flag: ${arg}`, "UNKNOWN_FLAG")
    if (spec.type === "boolean") {
      opts[spec.name] = inline === undefined ? true : !/^(false|0|no)$/i.test(inline)
      continue
    }
    let value = inline
    if (value === undefined) {
      const next = argv[i + 1]
      if (next === undefined || (next.startsWith("-") && !/^-\d/.test(next))) {
        throw new CliError(`flag --${spec.name} needs a value`, "MISSING_VALUE")
      }
      value = next
      i++
    }
    if (spec.type === "number") {
      const n = Number(value)
      if (!Number.isInteger(n) || n < 0) throw new CliError(`--${spec.name} must be a non-negative integer, got ${value}`, "INVALID_VALUE")
      opts[spec.name] = n
    } else {
      opts[spec.name] = value
    }
  }
  return { positional, opts }
}

function formatOf(opts: Opts): Format {
  const f = (opts.format as string | undefined) ?? "json"
  if (f !== "json" && f !== "table" && f !== "plain") throw new CliError(`--format must be json, table or plain, got ${f}`, "INVALID_VALUE")
  return f
}

/** Apply the client-side recency filter and 1-indexed page/limit window. */
export function windowResults(all: Job[], opts: Opts): Job[] {
  const recent = all.filter((j) => withinDays(j.date, opts.jobage as number | undefined))
  const limit = (opts.limit as number | undefined) ?? 25
  const page = Math.max((opts.page as number | undefined) ?? 1, 1)
  return recent.slice((page - 1) * limit, page * limit)
}

export async function runCli(spec: CliSpec, argv = process.argv.slice(2)): Promise<void> {
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
      const meta = { count: outcome.results.length, page: (opts.page as number | undefined) ?? 1, total: outcome.total ?? null, portal: spec.name }
      printSearch(outcome.results, meta, format)
      for (const w of outcome.warnings ?? []) process.stderr.write(JSON.stringify({ warning: w, code: "WARNING" }) + "\n")
      return
    }
    if (command === "detail") {
      const { positional, opts } = parseArgs(rest, [...COMMON_DETAIL, ...(spec.detailFlags ?? [])])
      const format = formatOf(opts)
      const id = positional[0]
      if (!id) throw new CliError("detail needs an id or URL", "MISSING_ARGUMENT")
      const job = await spec.detail(id, opts)
      if (!job) throw new CliError(`no posting found for ${id}`, "NOT_FOUND")
      printDetail(job, format)
      return
    }
    throw new CliError(`unknown command: ${command} (expected search or detail)`, "UNKNOWN_COMMAND")
  } catch (e) {
    if (e instanceof CliError) writeError(e.message, e.code)
    else writeError(e instanceof Error ? e.message : String(e), "UNEXPECTED_ERROR")
    process.exit(1)
  }
}
