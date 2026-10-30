import { CliError, type Job, type Opts } from "../helpers.ts"
import { extractJobPosting, fetchPostingPage, jobFromPosting } from "../page.ts"
import { fetchFeed, PORTAL, siteBase, UA } from "./search.ts"

/** The job page's JSON-LD when present; otherwise the RSS item (the feed carries the full text). */
export async function runDetail(ref: string, opts: Opts): Promise<Job | null> {
  const url = /^https?:\/\//.test(ref) ? ref : `${siteBase()}/remote-jobs/${ref.replace(/^\/+/, "")}`
  const host = new URL(url).hostname
  if (!/(^|\.)weworkremotely\.com$/.test(host) && !process.env.WWR_BASE_URL) throw new CliError(`${host} is not a We Work Remotely URL`, "INVALID_VALUE")
  const html = await fetchPostingPage(url, UA, PORTAL, "We Work Remotely")
  const posting = html ? extractJobPosting(html) : null
  if (posting) {
    const job = jobFromPosting(posting, url, PORTAL, url.replace(/^.*\/remote-jobs\//, ""))
    job.work_mode = job.work_mode ?? "remote"
    return job
  }
  const feed = await fetchFeed(String(opts.category ?? "all"))
  return feed.find((j) => j.url === url) ?? null
}
