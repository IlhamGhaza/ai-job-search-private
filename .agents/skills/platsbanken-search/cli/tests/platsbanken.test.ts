import { describe, expect, test } from "bun:test"
import { assertHttpFailures, json, mockServer, parseJSON, runCLI } from "./helpers"
import { hitToJob } from "../src/commands/search"

const HIT = {
  id: "31635810",
  webpage_url: "https://arbetsformedlingen.se/platsbanken/annonser/31635810",
  headline: "Flutterutvecklare",
  employer: { name: "Acme AB" },
  workplace_address: { municipality: "Stockholm", region: "Stockholms län", country: "Sverige" },
  publication_date: "2026-10-23T10:03:45",
  application_deadline: "2026-11-12T23:59:59",
  employment_type: { label: "Vanlig anställning" },
  salary_type: { label: "Fast månadslön" },
  salary_description: "35 000 kr/mån",
  experience_required: false,
  application_details: { url: "https://acme.example.com/apply" },
  description: { text: "Vi söker en Flutterutvecklare." },
  workplace_model: { label: null },
}

describe("platsbanken-search", () => {
  test("maps JobSearch hit fields; salary stays as stated text", () => {
    const job = hitToJob(HIT)
    expect(job.title).toBe("Flutterutvecklare")
    expect(job.country).toBe("Sverige")
    expect(job.deadline).toBe("2026-11-12")
    expect(job.salary_text).toBe("Fast månadslön: 35 000 kr/mån")
    expect(job.salary_min).toBeNull()
    expect(job.required_experience).toBe("no experience required")
    expect(job.work_mode).toBeNull()
  })

  test("search sends q, recency and the optional api-key header", async () => {
    let seenKey: string | null = null
    const server = mockServer((req) => {
      seenKey = req.headers.get("api-key")
      return json({ total: { value: 1 }, hits: [HIT] })
    })
    try {
      const out = parseJSON<{ meta: { total: number }; results: unknown[] }>(
        await runCLI(["search", "-q", "flutter OR dart", "--jobage", "2"], { JOBTECH_API_URL: server.url, JOBTECH_API_TOKEN: "test-key" }),
      )
      expect(out.meta.total).toBe(1)
      expect(server.hits[0]).toContain("q=flutter+dart")
      expect(server.hits[0]).toContain("published-after=2880")
      expect(seenKey).toBe("test-key")
    } finally {
      server.stop()
    }
  })

  test("works without a token (open API)", async () => {
    const server = mockServer(() => json({ total: { value: 0 }, hits: [] }))
    try {
      const r = await runCLI(["search", "-q", "flutter"], { JOBTECH_API_URL: server.url, JOBTECH_API_TOKEN: undefined })
      expect(r.exitCode).toBe(0)
    } finally {
      server.stop()
    }
  })

  test("HTTP errors, rate limit and unknown flags", async () => {
    await assertHttpFailures(["search", "-q", "flutter"], "JOBTECH_API_URL")
  })
})
