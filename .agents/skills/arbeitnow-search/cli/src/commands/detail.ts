import { CliError, type Job, type Opts } from "../helpers.ts"
import { extractJobPosting, fetchPostingPage, jobFromPosting } from "../page.ts"
import { apiBase, PORTAL, UA } from "./search.ts"

/** The job page's JSON-LD. A slug becomes /jobs/companies/... only via a full URL, so ask for one. */
export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  if (!/^https?:\/\//.test(ref)) throw new CliError("pass the Arbeitnow job URL from a search result's url field", "INVALID_VALUE")
  const host = new URL(ref).hostname
  if (!/(^|\.)arbeitnow\.com$/.test(host) && !ref.startsWith(apiBase())) throw new CliError(`${host} is not an Arbeitnow URL`, "INVALID_VALUE")
  const html = await fetchPostingPage(ref, UA, PORTAL, "Arbeitnow")
  if (html === null) return null
  const posting = extractJobPosting(html)
  if (!posting) throw new CliError("the page carries no JobPosting data; it may have closed", "NOT_FOUND")
  return jobFromPosting(posting, ref, PORTAL, ref.replace(/^.*\//, ""))
}
