// Single-posting page support for portals without a detail API: a robots.txt
// gate, then the schema.org JobPosting JSON-LD block most job pages embed for
// search engines. Only the one URL asked for is fetched - no crawling, no
// links followed. Same file in every skill that needs it; keep the copies equal.

import { CliError, contractDate, htmlToText, httpGet, makeJob, oneLine, payPeriod, positiveNumber, type Job } from "./helpers.ts"

interface RobotsRule {
  allow: boolean
  pattern: string
}

/** Rules that apply to `agentToken` (falling back to `*`), parsed from robots.txt. */
export function robotsRules(robots: string, agentToken: string): RobotsRule[] {
  const groups: { agents: string[]; rules: RobotsRule[] }[] = []
  let current: { agents: string[]; rules: RobotsRule[] } | null = null
  let lastWasAgent = false
  for (const raw of robots.split(/\r?\n/)) {
    const line = raw.replace(/#.*/, "").trim()
    const m = line.match(/^([A-Za-z-]+)\s*:\s*(.*)$/)
    if (!m) continue
    const field = m[1].toLowerCase()
    const value = m[2].trim()
    if (field === "user-agent") {
      if (!current || !lastWasAgent) {
        current = { agents: [], rules: [] }
        groups.push(current)
      }
      current.agents.push(value.toLowerCase())
      lastWasAgent = true
      continue
    }
    lastWasAgent = false
    if (!current) continue
    if (field === "allow" || field === "disallow") {
      if (field === "disallow" && value === "") continue
      current.rules.push({ allow: field === "allow", pattern: value })
    }
  }
  const token = agentToken.toLowerCase()
  const own = groups.filter((g) => g.agents.some((a) => a !== "*" && token.includes(a)))
  const chosen = own.length ? own : groups.filter((g) => g.agents.includes("*"))
  return chosen.flatMap((g) => g.rules)
}

function patternToRegex(pattern: string): RegExp {
  const anchored = pattern.endsWith("$")
  const body = (anchored ? pattern.slice(0, -1) : pattern)
    .split("*")
    .map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&"))
    .join(".*")
  return new RegExp("^" + body + (anchored ? "$" : ""))
}

/** Longest-match robots decision for a path (+query); ties go to allow. */
export function robotsAllowsPath(rules: RobotsRule[], pathAndQuery: string): boolean {
  let best: RobotsRule | null = null
  for (const r of rules) {
    if (!patternToRegex(r.pattern).test(pathAndQuery)) continue
    if (!best || r.pattern.length > best.pattern.length || (r.pattern.length === best.pattern.length && r.allow)) best = r
  }
  return best ? best.allow : true
}

/** Fetch `url` only if its host's robots.txt permits it for our agent. */
export async function fetchPostingPage(url: string, ua: string, agentToken: string, label: string): Promise<string | null> {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    throw new CliError(`not a URL: ${url}`, "INVALID_VALUE")
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") throw new CliError("only http(s) URLs", "INVALID_VALUE")
  const robots = await httpGet(`${parsed.origin}/robots.txt`, { label: `${label} robots.txt`, ua, accept: "text/plain" }).catch((e) => {
    if (e instanceof CliError && (e.code === "FORBIDDEN" || e.code === "UNAUTHORIZED")) {
      throw new CliError(`${label} refuses robots.txt to this client; paste the posting text instead`, "ROBOTS_DISALLOWED")
    }
    throw e
  })
  if (robots !== null && !robotsAllowsPath(robotsRules(robots, agentToken), parsed.pathname + parsed.search)) {
    throw new CliError(
      `${parsed.host}/robots.txt disallows ${parsed.pathname} for automated clients; open it in a browser and paste the posting into /apply`,
      "ROBOTS_DISALLOWED",
    )
  }
  return httpGet(url, { label, ua, accept: "text/html,application/xhtml+xml" })
}

type Json = Record<string, unknown>

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : v === undefined || v === null ? [] : [v]
}

function isJobPosting(node: unknown): node is Json {
  if (!node || typeof node !== "object") return false
  const t = (node as Json)["@type"]
  return asArray(t).some((x) => String(x).toLowerCase() === "jobposting")
}

/** The first schema.org JobPosting in the page's JSON-LD blocks, or null. */
export function extractJobPosting(html: string): Json | null {
  for (const m of html.matchAll(/<script[^>]+type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)) {
    let data: unknown
    try {
      data = JSON.parse(m[1].trim())
    } catch {
      // Some sites emit raw line breaks inside JSON strings; as whitespace
      // they are harmless outside strings and become spaces inside them.
      try {
        data = JSON.parse(m[1].replace(/[\r\n\t]+/g, " ").trim())
      } catch {
        continue
      }
    }
    const queue = [...asArray(data)]
    while (queue.length) {
      const node = queue.shift()
      if (isJobPosting(node)) return node
      if (node && typeof node === "object") queue.push(...asArray((node as Json)["@graph"]))
    }
  }
  return null
}

function str(v: unknown): string | null {
  if (v === null || v === undefined) return null
  if (typeof v === "object") return oneLine((v as Json).name ?? (v as Json)["@value"] ?? null)
  return oneLine(v)
}

/** Map a JobPosting JSON-LD node to the job record. Only stated values; the rest stay null. */
export function jobFromPosting(p: Json, url: string, portal: string, id: string): Job {
  const locations = asArray(p.jobLocation).map((l) => ((l as Json)?.address ?? {}) as Json)
  const addr = locations[0] ?? {}
  const country = str(addr.addressCountry)
  const location = [str(addr.addressLocality), str(addr.addressRegion), country].filter(Boolean).join(", ") || null
  const salary = (p.baseSalary ?? p.estimatedSalary) as Json | undefined
  const value = (salary?.value ?? {}) as Json
  const remote = String(p.jobLocationType ?? "").toUpperCase().includes("TELECOMMUTE")
  const eligibility = asArray(p.applicantLocationRequirements)
    .map((r) => str(r))
    .filter(Boolean)
    .join(", ")
  const exp = p.experienceRequirements as Json | string | undefined
  const months = typeof exp === "object" && exp ? positiveNumber(exp.monthsOfExperience) : null
  return makeJob({
    id,
    title: oneLine(p.title) ?? "(untitled)",
    company: str(p.hiringOrganization),
    location,
    date: contractDate(p.datePosted),
    url,
    portal,
    country,
    employment_type: asArray(p.employmentType).map((e) => String(e)).join(", ") || null,
    salary_min: positiveNumber(value.minValue ?? value.value),
    salary_max: positiveNumber(value.maxValue ?? value.value),
    salary_currency: (salary?.currency as string | undefined) ?? null,
    salary_period: payPeriod(value.unitText),
    remote_eligibility: eligibility || null,
    work_mode: remote ? "remote" : null,
    required_experience: months ? `${months} months` : typeof exp === "string" ? oneLine(exp) : null,
    deadline: contractDate(p.validThrough),
    apply_url: oneLine((p as Json).url) ?? null,
    evidence: ["schema.org JobPosting on the posting page"],
    description: htmlToText(p.description as string | undefined),
  })
}
