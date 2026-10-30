import { describe, expect, test } from "bun:test"
import { errorCode, json, mockServer, parseJSON, runCLI } from "./helpers"

const BRAVE = {
  web: {
    results: [
      { title: "Junior Flutter Developer Job in Jakarta - Jobstreet", url: "https://id.jobstreet.com/id/job/12345678", description: "PT Acme, Rp 6.000.000 - Rp 8.000.000 per month" },
      { title: "elsewhere", url: "https://example.org/job/1", description: "not jobstreet" },
    ],
  },
}

describe("jobstreet-search", () => {
  test("discovery returns unverified leads scoped to the chosen JobStreet site", async () => {
    const server = mockServer(() => json(BRAVE))
    try {
      const out = parseJSON<{ results: Array<Record<string, unknown>> }>(
        await runCLI(["search", "-q", "flutter", "--site", "id"], { BRAVE_SEARCH_API_URL: server.url, BRAVE_SEARCH_API_TOKEN: "k" }),
      )
      expect(out.results).toHaveLength(1)
      expect(out.results[0].verification_status).toBe("unverified_lead")
      expect(out.results[0].country).toBe("ID")
      expect(new URLSearchParams(server.hits[0].split("?")[1]).get("q")).toBe("site:id.jobstreet.com/job flutter")
    } finally {
      server.stop()
    }
  })

  test("detail never fetches JobStreet: MANUAL_ONLY", async () => {
    const r = await runCLI(["detail", "https://id.jobstreet.com/id/job/12345678"])
    expect(errorCode(r)).toBe("MANUAL_ONLY")
  })

  test("missing credentials and unknown sites", async () => {
    expect(errorCode(await runCLI(["search"], { BRAVE_SEARCH_API_TOKEN: undefined }))).toBe("MISSING_CREDENTIALS")
    expect(errorCode(await runCLI(["search", "--site", "zz"], { BRAVE_SEARCH_API_TOKEN: "k" }))).toBe("INVALID_VALUE")
  })

  test("a failing provider call becomes a warning per site, exit 0 with no results", async () => {
    const server = mockServer(() => new Response("", { status: 500 }))
    try {
      const r = await runCLI(["search", "--site", "id"], { BRAVE_SEARCH_API_URL: server.url, BRAVE_SEARCH_API_TOKEN: "k" })
      expect(r.exitCode).toBe(0)
      expect(r.stderr).toContain("JobStreet Indonesia")
    } finally {
      server.stop()
    }
  })

  test("unknown flags", async () => {
    const bad = await runCLI(["search", "--nope"])
    expect(errorCode(bad)).toBe("UNKNOWN_FLAG")
  })
})
