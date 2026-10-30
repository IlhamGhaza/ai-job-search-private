import { describe, expect, test } from "bun:test"
import { assertHttpFailures, errorCode, json, mockServer, parseJSON, runCLI } from "./helpers"
import { parseHimalayas } from "../src/commands/search"

const FIXTURE = {
  totalCount: 2,
  jobs: [
    {
      title: "Junior Flutter Developer",
      companyName: "Acme",
      employmentType: "Full Time",
      minSalary: 30000,
      maxSalary: 45000,
      currency: "USD",
      salaryPeriod: "annual",
      seniority: ["Entry-level"],
      locationRestrictions: [],
      timezoneRestrictions: [7, 8],
      description: "<p>Flutter</p>",
      pubDate: 1792087770,
      expiryDate: 1794679768,
      applicationLink: "https://himalayas.app/companies/acme/jobs/junior-flutter",
      guid: "https://himalayas.app/companies/acme/jobs/junior-flutter",
    },
    {
      title: "Senior Flutter Developer",
      companyName: "Beta",
      locationRestrictions: ["United States"],
      description: "x",
      pubDate: 1792087770,
      guid: "https://himalayas.app/companies/beta/jobs/senior-flutter",
      minSalary: null,
      maxSalary: null,
      currency: "USD",
    },
  ],
}

describe("himalayas-search", () => {
  test("an empty restriction list is recorded as such, never guessed", () => {
    const [a, b] = parseHimalayas(FIXTURE)
    expect(a.remote_eligibility).toBe("no location restriction listed")
    expect(a.salary_period).toBe("year")
    expect(a.seniority).toBe("Entry-level")
    expect(a.evidence.join(" ")).toContain("timezone")
    expect(b.remote_eligibility).toBe("United States")
    expect(b.salary_currency).toBeNull()
  })

  test("search passes q/country and applies the title filter", async () => {
    const server = mockServer(() => json(FIXTURE))
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(
        await runCLI(["search", "-q", "flutter", "--country", "ID", "--title-query", "junior"], { HIMALAYAS_API_URL: server.url }),
      )
      expect(out.results.map((r) => r.title)).toEqual(["Junior Flutter Developer"])
      expect(server.hits[0]).toBe("/jobs/api/search?q=flutter&country=ID")
    } finally {
      server.stop()
    }
  })

  test("paging is refused (robots.txt)", async () => {
    const r = await runCLI(["search", "-q", "flutter", "--page", "2"])
    expect(errorCode(r)).toBe("PAGE_DISALLOWED")
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "-q", "flutter"], "HIMALAYAS_API_URL")
  })
})
