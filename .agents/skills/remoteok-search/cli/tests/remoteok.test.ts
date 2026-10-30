import { describe, expect, test } from "bun:test"
import { assertHttpFailures, json, mockServer, parseJSON, runCLI } from "./helpers"
import { parseRemoteOk } from "../src/commands/search"

const FIXTURE = [
  { last_updated: 1, legal: "API Terms of Service: link back" },
  {
    id: "1137531",
    position: "Junior Flutter Dev",
    company: "Acme",
    location: "Worldwide",
    date: "2026-10-16T00:00:56+00:00",
    url: "https://remoteOK.com/remote-jobs/remote-junior-flutter-dev-acme-1137531",
    apply_url: "https://remoteOK.com/remote-jobs/1137531",
    salary_min: "40000",
    salary_max: "0",
    description: "<p>Flutter</p>",
  },
  { id: "1137532", position: "Designer", company: "Beta", location: "", date: "2026-10-15T00:00:00+00:00", url: "https://remoteok.com/remote-jobs/x-1137532", salary_min: 0, salary_max: 0, description: "Figma" },
]

describe("remoteok-search", () => {
  test("skips the legal element, reads USD/year salary, 0 means unstated", () => {
    const jobs = parseRemoteOk(FIXTURE)
    expect(jobs).toHaveLength(2)
    expect(jobs[0].salary_min).toBe(40000)
    expect(jobs[0].salary_max).toBeNull()
    expect(jobs[0].salary_currency).toBe("USD")
    expect(jobs[0].url.startsWith("https://remoteok.com/")).toBe(true)
    expect(jobs[1].salary_currency).toBeNull()
    expect(jobs[1].location).toBeNull()
  })

  test("search sends the tag and filters client-side", async () => {
    const server = mockServer(() => json(FIXTURE))
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(
        await runCLI(["search", "--tag", "flutter", "-q", "flutter"], { REMOTEOK_API_URL: server.url }),
      )
      expect(out.results.map((r) => r.title)).toEqual(["Junior Flutter Dev"])
      expect(server.hits[0]).toBe("/api?tag=flutter")
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "--tag", "flutter"], "REMOTEOK_API_URL")
  })
})
