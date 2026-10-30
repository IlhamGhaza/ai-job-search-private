import { join } from "path"

const CLI_PATH = join(import.meta.dir, "../src/cli.ts")

export interface CLIResult {
  stdout: string
  stderr: string
  exitCode: number
}

/** Run the CLI as a subprocess. `env` overrides are merged over a scrubbed environment. */
export async function runCLI(args: string[], env: Record<string, string | undefined> = {}): Promise<CLIResult> {
  const merged: Record<string, string> = {}
  for (const [k, v] of Object.entries({ ...process.env, PORTAL_RETRY_BASE_MS: "1", PORTAL_MAX_RETRIES: "1", ...env })) {
    if (v !== undefined) merged[k] = v
  }
  const proc = Bun.spawn(["bun", "run", CLI_PATH, ...args], { stdout: "pipe", stderr: "pipe", env: merged })
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ])
  return { stdout: stdout.trim(), stderr: stderr.trim(), exitCode }
}

export function parseJSON<T = unknown>(result: CLIResult): T {
  if (result.exitCode !== 0) throw new Error(`CLI exited with code ${result.exitCode}. stderr: ${result.stderr}`)
  return JSON.parse(result.stdout) as T
}

export function errorCode(result: CLIResult): string | null {
  const line = result.stderr.split("\n").find((l) => l.includes('"code"'))
  if (!line) return null
  try {
    return (JSON.parse(line) as { code?: string }).code ?? null
  } catch {
    return null
  }
}

type Route = (req: Request) => Response | Promise<Response>

/** A local HTTP server standing in for the portal: no live calls in tests. */
export function mockServer(route: Route): { url: string; stop: () => void; hits: string[] } {
  const hits: string[] = []
  const server = Bun.serve({
    port: 0,
    fetch(req) {
      const u = new URL(req.url)
      hits.push(u.pathname + u.search)
      return route(req)
    },
  })
  return { url: `http://127.0.0.1:${server.port}`, stop: () => server.stop(true), hits }
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

/** Assert the contract fields every portal emits, with null (never undefined) for missing values. */
export function contractOk(job: Record<string, unknown>): boolean {
  return ["id", "title", "company", "location", "date", "url"].every((k) => k in job && job[k] !== undefined)
}

/**
 * The contract's failure modes against a mock server: a persistent 5xx exits 1
 * with HTTP_ERROR, a persistent 429 with RATE_LIMITED, an unknown flag with
 * UNKNOWN_FLAG. `envVar` points the CLI at the mock instead of the portal.
 */
export async function assertHttpFailures(args: string[], envVar: string, extraEnv: Record<string, string> = {}): Promise<void> {
  const { expect } = await import("bun:test")
  for (const [status, code] of [
    [500, "HTTP_ERROR"],
    [429, "RATE_LIMITED"],
  ] as const) {
    const server = mockServer(() => new Response("", { status }))
    try {
      const r = await runCLI(args, { [envVar]: server.url, ...extraEnv })
      expect(r.exitCode).toBe(1)
      expect(errorCode(r)).toBe(code)
      expect(r.stdout).toBe("")
    } finally {
      server.stop()
    }
  }
  const bad = await runCLI([...args, "--no-such-flag"], extraEnv)
  expect(bad.exitCode).toBe(1)
  expect(errorCode(bad)).toBe("UNKNOWN_FLAG")
}
