import { describe, expect, test } from "bun:test"
import { assertHttpFailures, json, mockServer, parseJSON, runCLI } from "./helpers"
import { parseArbeitnow } from "../src/commands/search"

const now = Math.floor(Date.now() / 1000)
const FIXTURE = {
  data: [
    { slug: "flutter-dev-1", company_name: "Acme", title: "Junior Flutter Developer (m/w/d)", description: "&lt;p&gt;Flutter&lt;/p&gt;", remote: true, url: "https://www.arbeitnow.com/jobs/companies/acme/flutter-dev-1", tags: [], job_types: ["full time"], location: "Berlin", created_at: now },
    { slug: "werkstudent-2", company_name: "Beta", title: "Working Student Marketing", description: "Marketing", remote: false, url: "https://www.arbeitnow.com/jobs/companies/beta/werkstudent-2", tags: [], job_types: [], location: "Munich", created_at: now },
  ],
  links: { next: null },
}

describe("arbeitnow-search", () => {
  test("decodes escaped HTML; the visa filter is recorded as a portal tag only", () => {
    const [a] = parseArbeitnow(FIXTURE, true)
    expect(a.description).toBe("Flutter")
    expect(a.work_mode).toBe("remote")
    expect(a.visa_sponsorship).toContain("unconfirmed")
    const [b] = parseArbeitnow(FIXTURE, false)
    expect(b.visa_sponsorship).toBeNull()
  })

  test("search passes the visa filter and matches client-side", async () => {
    const server = mockServer(() => json(FIXTURE))
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(
        await runCLI(["search", "-q", "flutter", "--visa"], { ARBEITNOW_API_URL: server.url }),
      )
      expect(out.results.map((r) => r.title)).toEqual(["Junior Flutter Developer (m/w/d)"])
      expect(server.hits[0]).toContain("visa_sponsorship=true")
      expect(server.hits).toHaveLength(1)
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "-q", "flutter"], "ARBEITNOW_API_URL")
  })
})
