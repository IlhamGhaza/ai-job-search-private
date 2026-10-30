import { CliError, getJson, type Job, type Opts } from "../helpers.ts"
import { adToJob, apiBase, token, UA } from "./search.ts"

export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  const uuid = ref.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)?.[0]
  if (!uuid) throw new CliError(`cannot read ${ref}: pass a NAV ad uuid or arbeidsplassen.nav.no URL`, "INVALID_VALUE")
  const entry = await getJson<Record<string, unknown>>(`${apiBase()}/api/v1/feedentry/${uuid}`, {
    label: "NAV job feed",
    ua: UA,
    headers: { Authorization: `Bearer ${await token()}` },
  })
  return entry ? adToJob(entry) : null
}
