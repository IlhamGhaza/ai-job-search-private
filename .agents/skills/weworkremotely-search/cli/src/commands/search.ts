import { baseFromEnv, contractDate, decodeEntities, htmlToText, httpGet, makeJob, oneLine, queryMatcher, userAgent, windowResults, type Job, type Opts, type SearchOutcome } from "../helpers.ts"

export const PORTAL = "weworkremotely-search"
export const UA = userAgent(PORTAL)

export function siteBase(): string {
  return baseFromEnv("WWR_BASE_URL", "https://weworkremotely.com")
}

function tag(item: string, name: string): string | null {
  const m = item.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`, "i"))
  if (!m) return null
  const raw = m[1].replace(/^<!\[CDATA\[([\s\S]*?)\]\]>$/, "$1").trim()
  return raw || null
}

/** RSS items, one chunk each, so one malformed item cannot break the rest. Titles are "Company: Role". */
export function parseRss(xml: string): Job[] {
  const jobs: Job[] = []
  for (const chunk of xml.split(/<item>/i).slice(1)) {
    const item = chunk.split(/<\/item>/i)[0]
    const link = tag(item, "link") ?? tag(item, "guid")
    const rawTitle = oneLine(decodeEntities(tag(item, "title") ?? ""))
    if (!link || !rawTitle) continue
    const sep = rawTitle.indexOf(": ")
    const company = sep > 0 ? rawTitle.slice(0, sep) : null
    const title = sep > 0 ? rawTitle.slice(sep + 2) : rawTitle
    const region = oneLine(decodeEntities(tag(item, "region") ?? ""))
    const description = htmlToText(decodeEntities(tag(item, "description") ?? ""))
    const hq = description?.match(/Headquarters:\s*([^\n]+)/)?.[1]?.trim() ?? null
    jobs.push(
      makeJob({
        id: link.replace(/^.*\/remote-jobs\//, ""),
        title,
        company,
        location: region,
        date: contractDate(tag(item, "pubDate")),
        url: link,
        portal: PORTAL,
        employment_type: oneLine(tag(item, "type")),
        remote_eligibility: region,
        work_mode: "remote",
        evidence: ["We Work Remotely RSS feed", ...(hq ? [`headquarters: ${hq}`] : [])],
        description,
      }),
    )
  }
  return jobs
}

export async function fetchFeed(category: string): Promise<Job[]> {
  const path = category === "all" ? "/remote-jobs.rss" : `/categories/${encodeURIComponent(category)}.rss`
  const xml = await httpGet(`${siteBase()}${path}`, { label: "We Work Remotely RSS", ua: UA, accept: "application/rss+xml, application/xml" })
  return xml ? parseRss(xml) : []
}

export async function runSearch(opts: Opts): Promise<SearchOutcome> {
  const jobs = await fetchFeed(String(opts.category ?? "remote-programming-jobs"))
  const match = queryMatcher(opts.query as string | undefined)
  const matchLoc = queryMatcher(opts.location as string | undefined)
  const filtered = jobs.filter((j) => match(`${j.title}\n${j.description ?? ""}`) && matchLoc(j.location ?? ""))
  return { results: windowResults(filtered, opts), total: filtered.length }
}
