import { describe, expect, test } from "bun:test"
import { assertHttpFailures, mockServer, parseJSON, runCLI } from "./helpers"
import { parseRss } from "../src/commands/search"

const RSS = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Acme: Junior Flutter Developer</title>
  <region>Anywhere in the World</region>
  <category>Mobile</category>
  <type>Full-Time</type>
  <description>&lt;p&gt;&lt;strong&gt;Headquarters:&lt;/strong&gt; Jakarta&lt;/p&gt;&lt;p&gt;Flutter apps&lt;/p&gt;</description>
  <pubDate>Sun, 11 Oct 2026 07:31:07 +0000</pubDate>
  <guid>https://weworkremotely.com/remote-jobs/acme-junior-flutter-developer</guid>
  <link>https://weworkremotely.com/remote-jobs/acme-junior-flutter-developer</link>
</item>
<item><title>broken item without link</title></item>
<item>
  <title>Beta: Senior Rails Engineer</title>
  <region>USA Only</region>
  <description>Rails</description>
  <pubDate>Sat, 10 Oct 2026 07:31:07 +0000</pubDate>
  <link>https://weworkremotely.com/remote-jobs/beta-senior-rails</link>
</item>
</channel></rss>`

describe("weworkremotely-search", () => {
  test("RSS items parse independently; Company: Title split; region kept", () => {
    const jobs = parseRss(RSS)
    expect(jobs).toHaveLength(2)
    expect(jobs[0].company).toBe("Acme")
    expect(jobs[0].title).toBe("Junior Flutter Developer")
    expect(jobs[0].remote_eligibility).toBe("Anywhere in the World")
    expect(jobs[0].date).toBe("2026-10-11")
    expect(jobs[0].evidence).toContain("headquarters: Jakarta")
  })

  test("search filters by query and region", async () => {
    const server = mockServer(() => new Response(RSS, { headers: { "Content-Type": "application/rss+xml" } }))
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(
        await runCLI(["search", "-q", "flutter OR rails", "-l", "anywhere"], { WWR_BASE_URL: server.url }),
      )
      expect(out.results.map((r) => r.title)).toEqual(["Junior Flutter Developer"])
      expect(server.hits[0]).toBe("/categories/remote-programming-jobs.rss")
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search"], "WWR_BASE_URL")
  })
})
