import { CliError, type Job, type Opts } from "../helpers.ts"
import { fetchJobs } from "./search.ts"

/**
 * Remotive has no single-job endpoint: detail re-reads the category feed (one
 * call) and picks the id. Prefer the description already in search output.
 */
export async function runDetail(ref: string, opts: Opts): Promise<Job | null> {
  const id = ref.match(/(\d{4,})\/?$/)?.[1] ?? (/^\d+$/.test(ref) ? ref : null)
  if (!id) throw new CliError(`cannot read ${ref}: pass a Remotive job id or job URL`, "INVALID_VALUE")
  const jobs = await fetchJobs({ category: opts.category })
  return jobs.find((j) => j.id === id || j.url.endsWith(`-${id}`)) ?? null
}
