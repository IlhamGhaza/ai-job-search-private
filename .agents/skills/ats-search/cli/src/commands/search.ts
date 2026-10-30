import { readFileSync } from "fs"
import { join } from "path"
import { CliError, queryMatcher, windowResults, type Job, type Opts, type SearchOutcome } from "../helpers.ts"
import { ATS_NAMES, fetchBoard, type AtsName, type Company } from "../providers.ts"

/** The company list shipped beside SKILL.md; --companies points elsewhere. */
export const DEFAULT_COMPANIES = join(import.meta.dir, "..", "..", "..", "companies.json")

export function loadCompanies(path: string): Company[] {
  let raw: unknown
  try {
    raw = JSON.parse(readFileSync(path, "utf-8"))
  } catch (e) {
    throw new CliError(`cannot read company list ${path}: ${e instanceof Error ? e.message : String(e)}`, "BAD_CONFIG")
  }
  const list = (raw as { companies?: unknown })?.companies
  if (!Array.isArray(list)) throw new CliError(`${path} must hold {"companies": [...]}`, "BAD_CONFIG")
  return list.map((c, i) => {
    const entry = c as Record<string, unknown>
    const ats = String(entry.ats ?? "").toLowerCase()
    if (!(ATS_NAMES as readonly string[]).includes(ats)) {
      throw new CliError(`companies[${i}]: ats must be one of ${ATS_NAMES.join(", ")}, got ${entry.ats}`, "BAD_CONFIG")
    }
    if (typeof entry.board !== "string" || !/^[A-Za-z0-9_.-]+$/.test(entry.board)) {
      throw new CliError(`companies[${i}]: board must be the ATS board slug`, "BAD_CONFIG")
    }
    return { name: String(entry.name ?? entry.board), ats: ats as AtsName, board: entry.board }
  })
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  let companies = loadCompanies((opts.companies as string | undefined) ?? DEFAULT_COMPANIES)
  if (opts.company) {
    const want = String(opts.company).toLowerCase()
    companies = companies.filter((c) => c.name.toLowerCase().includes(want) || c.board.toLowerCase() === want)
  }
  if (opts.ats) {
    const want = String(opts.ats).toLowerCase()
    if (!(ATS_NAMES as readonly string[]).includes(want)) throw new CliError(`--ats must be one of ${ATS_NAMES.join(", ")}`, "INVALID_VALUE")
    companies = companies.filter((c) => c.ats === want)
  }
  if (!companies.length) throw new CliError("no company in the list matches the filters", "NO_COMPANIES")

  const matchText = queryMatcher(opts.query as string | undefined)
  const matchTitle = queryMatcher(opts["title-query"] as string | undefined)
  const matchLocation = queryMatcher(opts.location as string | undefined)
  const warnings: string[] = []
  const pool: Job[] = []
  // One company at a time: a handful of boards, politely sequential.
  for (const c of companies) {
    try {
      const jobs = await fetchBoard(c)
      if (!jobs.length) warnings.push(`${c.name} (${c.ats}:${c.board}): board empty or not found`)
      pool.push(...jobs)
    } catch (e) {
      // One failing board must not sink the run.
      warnings.push(`${c.name} (${c.ats}:${c.board}): ${e instanceof Error ? e.message : String(e)}`)
    }
  }
  const matched = pool.filter(
    (j) =>
      matchText(`${j.title}\n${j.description ?? ""}`) &&
      matchTitle(j.title) &&
      matchLocation(`${j.location ?? ""} ${j.country ?? ""} ${j.work_mode ?? ""}`),
  )
  matched.sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""))
  const results = windowResults(matched, opts)
  if (opts["no-description"]) for (const j of results) j.description = null
  return { results, total: matched.length, warnings }
}
