import { describe, expect, test } from "bun:test"
import { assertHttpFailures, errorCode, json, mockServer, parseJSON, runCLI } from "./helpers"
import { adToJob, parseFeedPage } from "../src/commands/search"

const UUID = "fc12155d-04fd-4887-92cb-011ed541f443"
const ENTRY = {
  uuid: UUID,
  status: "ACTIVE",
  ad_content: {
    uuid: UUID,
    published: "2026-10-30T01:47:10.555249+01:00",
    expires: "2026-11-16T22:59:59+01:00",
    workLocations: [{ country: "NORGE", city: "OSLO", county: "OSLO" }],
    contactList: [{ name: "Private Person", email: "person@example.com" }],
    title: "Flutter-utvikler",
    description: "<p>Vi søker en apputvikler</p>",
    applicationUrl: "https://acme.example.com/apply",
    applicationDue: "2026-11-16T00:00:00Z",
    link: `https://arbeidsplassen.nav.no/stillinger/stilling/${UUID}`,
    employer: { name: "Acme AS" },
    engagementtype: "Fast",
    extent: "Heltid",
  },
}

describe("nav-search", () => {
  test("ad mapping drops contact persons", () => {
    const job = adToJob(ENTRY)
    expect(job.title).toBe("Flutter-utvikler")
    expect(job.employment_type).toBe("Fast, Heltid")
    expect(JSON.stringify(job)).not.toContain("person@example.com")
  })

  test("feed page parsing reads status and next link", () => {
    const page = parseFeedPage({ items: [{ id: UUID, _feed_entry: { uuid: UUID, status: "INACTIVE", title: "x", businessName: "y" } }], next_url: "/api/v1/feed/abc" })
    expect(page.items[0].status).toBe("INACTIVE")
    expect(page.next).toBe("/api/v1/feed/abc")
  })

  test("search uses the public token, If-Modified-Since, compound-word matching", async () => {
    let auth: string | null = null
    let ims: string | null = null
    const server = mockServer((req) => {
      const path = new URL(req.url).pathname
      if (path === "/api/publicToken") return new Response("Current public token:\naaa.bbb.ccc\n")
      if (path === "/api/v1/feed") {
        auth = req.headers.get("authorization")
        ims = req.headers.get("if-modified-since")
        return json({
          items: [
            { id: UUID, _feed_entry: { uuid: UUID, status: "ACTIVE", title: "Flutter-utvikler", businessName: "Acme AS" } },
            { id: "x", _feed_entry: { uuid: "00000000-0000-0000-0000-000000000000", status: "ACTIVE", title: "Sykepleier", businessName: "Z" } },
          ],
          next_url: null,
        })
      }
      if (path.startsWith("/api/v1/feedentry/")) return json(ENTRY)
      return new Response("", { status: 404 })
    })
    try {
      const out = parseJSON<{ results: Array<{ title: string }> }>(
        await runCLI(["search", "-q", "utvikler"], { NAV_FEED_URL: server.url, NAV_API_TOKEN: undefined }),
      )
      expect(out.results.map((r) => r.title)).toEqual(["Flutter-utvikler"])
      expect(auth).toBe("Bearer aaa.bbb.ccc")
      expect(ims).not.toBeNull()
    } finally {
      server.stop()
    }
  })

  test("a missing public token is MISSING_CREDENTIALS", async () => {
    const server = mockServer(() => new Response("no token today"))
    try {
      const r = await runCLI(["search", "-q", "x"], { NAV_FEED_URL: server.url, NAV_API_TOKEN: undefined })
      expect(errorCode(r)).toBe("MISSING_CREDENTIALS")
    } finally {
      server.stop()
    }
  })

  test("--query is required", async () => {
    expect(errorCode(await runCLI(["search"]))).toBe("MISSING_VALUE")
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "-q", "flutter"], "NAV_FEED_URL", { NAV_API_TOKEN: "own.token.here" })
  })
})
