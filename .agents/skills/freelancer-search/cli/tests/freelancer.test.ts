import { describe, expect, test } from "bun:test"
import { assertHttpFailures, errorCode, json, mockServer, parseJSON, runCLI } from "./helpers"
import { parseProject } from "../src/commands/search"

const PROJECT = {
  id: 39000001,
  title: "Flutter app bug fixes",
  seo_url: "mobile-phone/flutter-app-bug-fixes",
  type: "hourly",
  currency: { code: "USD" },
  budget: { minimum: 8, maximum: 15 },
  bid_stats: { bid_count: 12 },
  time_submitted: 1761696000,
  owner_id: 77,
  jobs: [{ name: "Flutter" }, { name: "Firebase" }],
  description: "Fix crashes in our Flutter app.​",
  hourly_project_info: { duration_enum: "month" },
}
const LOCAL = { id: 39000002, title: "Flutter dev at our office", type: "fixed", local: true, currency: { code: "INR" }, budget: { minimum: 10000 }, owner_id: 78 }
const USERS = {
  "77": { location: { country: { name: "Australia" } }, status: { payment_verified: true }, employer_reputation: { entire_history: { overall: 4.9, complete: 14 } } },
}
const ANSWER = { status: "success", result: { projects: [PROJECT, LOCAL], users: USERS, total_count: 2 } }

describe("freelancer-search", () => {
  test("parser maps project and owner; unknown owner stays null", () => {
    const g = parseProject(PROJECT, USERS["77"])!
    expect(g.url).toBe("https://www.freelancer.com/projects/mobile-phone/flutter-app-bug-fixes")
    expect([g.budget_type, g.budget_min, g.budget_max, g.budget_currency]).toEqual(["hourly", 8, 15, "USD"])
    expect([g.client_country, g.client_verified_payment, g.client_rating, g.client_hires]).toEqual(["Australia", true, 4.9, 14])
    expect(g.client_total_spent).toBeNull()
    expect(g.proposals_count).toBe(12)
    expect(g.est_duration).toBe("1 week to 1 month")
    expect(g.skills).toEqual(["Flutter", "Firebase"])
    const local = parseProject(LOCAL, null)!
    expect(local.client_verified_payment).toBeNull()
    expect(local.evidence.join(" ")).toContain("onsite:")
  })

  test("search calls the active-projects endpoint with the oauth header", async () => {
    let header = ""
    const server = mockServer((req) => {
      header = req.headers.get("freelancer-oauth-v1") ?? ""
      return json(ANSWER)
    })
    try {
      const r = await runCLI(["search", "-q", "flutter"], { FREELANCER_API_URL: server.url, FREELANCER_OAUTH_TOKEN: "tok" })
      const out = parseJSON<{ results: Array<{ gig_id: string; description: string }> }>(r)
      expect(out.results.map((g) => g.gig_id)).toEqual(["39000001", "39000002"])
      expect(out.results[0].description).toBe("Fix crashes in our Flutter app.")
      expect(header).toBe("tok")
      expect(server.hits[0]).toContain("/projects/0.1/projects/active/")
      expect(r.stdout).not.toContain("tok")
    } finally {
      server.stop()
    }
  })

  test("missing token: MISSING_CREDENTIALS before any request", async () => {
    const r = await runCLI(["search"], { FREELANCER_OAUTH_TOKEN: undefined })
    expect(r.exitCode).toBe(1)
    expect(errorCode(r)).toBe("MISSING_CREDENTIALS")
  })

  test("HTTP errors, rate limit and unknown flags fail with JSON errors", async () => {
    await assertHttpFailures(["search"], "FREELANCER_API_URL", { FREELANCER_OAUTH_TOKEN: "tok" })
  })

  test("detail resolves a project URL through the API, then its owner", async () => {
    const server = mockServer((req) => {
      const u = new URL(req.url)
      if (u.pathname.startsWith("/users/")) return json({ status: "success", result: USERS["77"] })
      return json({ status: "success", result: { projects: [PROJECT] } })
    })
    try {
      const g = parseJSON<{ gig_id: string; client_country: string }>(
        await runCLI(["detail", "https://www.freelancer.co.id/projects/mobile-phone/flutter-app-bug-fixes"], {
          FREELANCER_API_URL: server.url,
          FREELANCER_OAUTH_TOKEN: "tok",
        }),
      )
      expect(g.gig_id).toBe("39000001")
      expect(g.client_country).toBe("Australia")
      expect(server.hits[0]).toContain("seo_urls")
    } finally {
      server.stop()
    }
  })
})
