import { describe, expect, test } from "bun:test"
import { assertHttpFailures, json, mockServer, parseJSON, runCLI } from "./helpers"
import { parseJobicy } from "../src/commands/search"

const FIXTURE = {
  friendlyNotice: "credit Jobicy",
  jobs: [
    {
      id: 1,
      url: "https://jobicy.com/jobs/1-junior-flutter",
      jobTitle: "Junior Flutter Engineer",
      companyName: "Acme",
      jobType: ["Full-Time"],
      jobGeo: "APAC",
      jobLevel: "Junior",
      jobDescription: "<p>Flutter &amp; Dart</p>",
      pubDate: "2026-10-26T13:22:25+00:00",
      salaryMin: 24000,
      salaryMax: 36000,
      salaryCurrency: "USD",
      salaryPeriod: "yearly",
    },
    { id: 2, url: "https://jobicy.com/jobs/2-marketing", jobTitle: "Marketing Lead", companyName: "Beta", jobGeo: "USA", jobDescription: "marketing", pubDate: "2026-10-26" },
  ],
}

describe("jobicy-search", () => {
  test("maps geo, level and yearly salary", () => {
    const [job] = parseJobicy(FIXTURE)
    expect(job.remote_eligibility).toBe("APAC")
    expect(job.seniority).toBe("Junior")
    expect(job.salary_period).toBe("year")
    expect(job.employment_type).toBe("Full-Time")
    expect(job.description).toBe("Flutter & Dart")
  })

  test("search filters client-side", async () => {
    const server = mockServer(() => json(FIXTURE))
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(
        await runCLI(["search", "--tag", "flutter", "--geo", "apac", "-q", "flutter"], { JOBICY_API_URL: server.url }),
      )
      expect(out.results.map((r) => r.title)).toEqual(["Junior Flutter Engineer"])
      expect(server.hits[0]).toContain("geo=apac")
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "--tag", "flutter"], "JOBICY_API_URL")
  })
})
