import { describe, expect, test } from "bun:test"
import { assertHttpFailures, errorCode, json, mockServer, parseJSON, runCLI } from "./helpers"
import { buildQuery, isPostUrl } from "../src/commands/search"

const BRAVE = {
  web: {
    results: [
      { title: "Jane Doe on LinkedIn: We're hiring a Junior Flutter Developer in Jakarta", url: "https://www.linkedin.com/posts/janedoe_hiring-flutter-activity-1", description: "DM me your CV" },
      { title: "Acme | LinkedIn", url: "https://www.linkedin.com/company/acme", description: "company page" },
      { title: "phish", url: "https://linkedin.com.evil.example/posts/x", description: "x" },
    ],
  },
}

describe("linkedin-posts-search", () => {
  test("only public post URLs on linkedin.com hosts count", () => {
    expect(isPostUrl("https://www.linkedin.com/posts/a_b-activity-1")).toBe(true)
    expect(isPostUrl("https://www.linkedin.com/feed/update/urn:li:activity:1")).toBe(true)
    expect(isPostUrl("https://www.linkedin.com/jobs/view/1")).toBe(false)
    expect(isPostUrl("https://linkedin.com.evil.example/posts/x")).toBe(false)
  })

  test("query is site-scoped with hiring words", () => {
    expect(buildQuery({ query: '"junior flutter"', location: "Singapore" })).toBe(
      'site:linkedin.com/posts "junior flutter" (hiring OR "we are hiring" OR "join our team") "Singapore"',
    )
    expect(buildQuery({ query: "x y", raw: true })).toBe("x y")
  })

  test("results are unverified social-post leads with query, snippet and discovered_at", async () => {
    let token: string | null = null
    const server = mockServer((req) => {
      token = req.headers.get("x-subscription-token")
      return json(BRAVE)
    })
    try {
      const out = parseJSON<{ results: Array<Record<string, unknown>> }>(
        await runCLI(["search", "-q", "flutter"], { BRAVE_SEARCH_API_URL: server.url, BRAVE_SEARCH_API_TOKEN: "k" }),
      )
      expect(out.results).toHaveLength(1)
      const lead = out.results[0]
      expect(lead.source_type).toBe("social_post")
      expect(lead.verification_status).toBe("unverified_lead")
      expect(lead.company).toBeNull()
      expect(lead.poster).toBe("Jane Doe")
      expect(lead.snippet).toBe("DM me your CV")
      expect(String(lead.query)).toContain("site:linkedin.com/posts")
      expect(typeof lead.discovered_at).toBe("string")
      expect(token).toBe("k")
    } finally {
      server.stop()
    }
  })

  test("missing BRAVE_SEARCH_API_TOKEN is MISSING_CREDENTIALS, before any request", async () => {
    const server = mockServer(() => json(BRAVE))
    try {
      const r = await runCLI(["search"], { BRAVE_SEARCH_API_URL: server.url, BRAVE_SEARCH_API_TOKEN: undefined })
      expect(r.exitCode).toBe(1)
      expect(errorCode(r)).toBe("MISSING_CREDENTIALS")
      expect(server.hits).toHaveLength(0)
      expect(r.stderr).not.toContain("X-Subscription")
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search"], "BRAVE_SEARCH_API_URL", { BRAVE_SEARCH_API_TOKEN: "k" })
  })
})
