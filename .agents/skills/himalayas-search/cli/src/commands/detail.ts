import { CliError, type Job, type Opts } from "../helpers.ts"
import { extractJobPosting, fetchPostingPage, jobFromPosting } from "../page.ts"
import { apiBase, PORTAL, UA } from "./search.ts"

/** A Himalayas job page's JSON-LD (robots.txt allows /companies/<c>/jobs/<slug>). */
export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  const url = /^https?:\/\//.test(ref) ? ref : `${apiBase()}/companies/${ref.replace(/^\/+/, "")}`
  const host = new URL(url).hostname
  if (!/(^|\.)himalayas\.app$/.test(host) && !process.env.HIMALAYAS_API_URL) {
    throw new CliError(`${host} is not a Himalayas URL`, "INVALID_VALUE")
  }
  const html = await fetchPostingPage(url, UA, PORTAL, "Himalayas").catch((e) => {
    // Job pages answer 403 to non-browser clients (seen 2026-10-30). Not worked
    // around: the search result already carries the full description.
    if (e instanceof CliError && e.code === "FORBIDDEN") {
      throw new CliError("Himalayas blocks automated reads of job pages (403); use the search result's description, or paste the posting into /apply", "FORBIDDEN")
    }
    throw e
  })
  if (html === null) return null
  const posting = extractJobPosting(html)
  if (!posting) throw new CliError("the page carries no JobPosting data; it may have closed", "NOT_FOUND")
  const job = jobFromPosting(posting, url, PORTAL, url)
  job.work_mode = job.work_mode ?? "remote"
  return job
}
