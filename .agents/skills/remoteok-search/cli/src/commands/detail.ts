import { CliError, type Job, type Opts } from "../helpers.ts"
import { fetchJobs } from "./search.ts"

/** No single-job endpoint: re-read the feed (one call) and pick the id. */
export async function runDetail(ref: string, opts: Opts): Promise<Job | null> {
  const id = ref.match(/(\d{5,})\/?$/)?.[1]
  if (!id) throw new CliError(`cannot read ${ref}: pass a Remote OK job id or job URL`, "INVALID_VALUE")
  const jobs = await fetchJobs(opts.tag as string | undefined)
  return jobs.find((j) => j.id === id) ?? null
}
