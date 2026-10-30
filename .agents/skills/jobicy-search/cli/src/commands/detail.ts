import { CliError, type Job, type Opts } from "../helpers.ts"
import { extractJobPosting, fetchPostingPage, jobFromPosting } from "../page.ts"
import { apiBase, PORTAL, UA } from "./search.ts"

/** A Jobicy job page's JSON-LD; an id becomes /jobs/<id>. */
export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  const url = /^https?:\/\//.test(ref) ? ref : `${apiBase()}/jobs/${ref.replace(/^\/+/, "")}`
  const host = new URL(url).hostname
  if (!/(^|\.)jobicy\.com$/.test(host) && !process.env.JOBICY_API_URL) throw new CliError(`${host} is not a Jobicy URL`, "INVALID_VALUE")
  const html = await fetchPostingPage(url, UA, PORTAL, "Jobicy")
  if (html === null) return null
  const posting = extractJobPosting(html)
  if (!posting) throw new CliError("the page carries no JobPosting data; it may have closed", "NOT_FOUND")
  const job = jobFromPosting(posting, url, PORTAL, ref)
  job.work_mode = job.work_mode ?? "remote"
  return job
}
