import { describe, expect, test } from "bun:test"
import { assertHttpFailures, json, mockServer, parseJSON, runCLI } from "./helpers"
import { mcfToJob } from "../src/commands/search"

const JOB = {
  uuid: "cacb464bcc98690b05b0c196bc5a21df",
  title: "Junior Flutter Developer",
  minimumYearsExperience: 1,
  employmentTypes: [{ employmentType: "Full Time" }],
  positionLevels: [{ position: "Junior Executive" }],
  postedCompany: { name: "ACME PTE. LTD." },
  address: { isOverseas: false, districts: [{ location: "Islandwide" }] },
  metadata: { newPostingDate: "2026-10-28", expiryDate: "2026-11-27", isHideSalary: false, jobDetailsUrl: "https://www.mycareersfuture.gov.sg/job/information-technology/junior-flutter-developer-acme-cacb464bcc98690b05b0c196bc5a21df" },
  salary: { minimum: 3000, maximum: 4000, type: { salaryType: "Monthly" } },
  description: "<p>Flutter</p>",
}

describe("mycareersfuture-search", () => {
  test("maps SGD monthly gross salary, experience and level", () => {
    const job = mcfToJob(JOB)
    expect(job.salary_currency).toBe("SGD")
    expect(job.salary_period).toBe("month")
    expect(job.salary_gross_or_net).toBe("gross")
    expect(job.required_experience).toBe("1+ years")
    expect(job.seniority).toBe("Junior Executive")
    expect(job.url).toContain("mycareersfuture.gov.sg/job/")
  })

  test("a hidden salary stays null", () => {
    const job = mcfToJob({ ...JOB, metadata: { ...JOB.metadata, isHideSalary: true } })
    expect(job.salary_min).toBeNull()
    expect(job.salary_currency).toBeNull()
  })

  test("search passes the query and 0-indexed page", async () => {
    const server = mockServer(() => json({ results: [JOB], total: 1 }))
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(await runCLI(["search", "-q", "flutter", "--page", "2"], { MCF_API_URL: server.url }))
      expect(out.results).toHaveLength(1)
      expect(server.hits[0]).toContain("search=flutter")
      expect(server.hits[0]).toContain("page=1")
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "-q", "flutter"], "MCF_API_URL")
  })
})
