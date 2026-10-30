import { CliError, getJson, type Job, type Opts } from "../helpers.ts"
import { apiBase, mcfToJob, UA } from "./search.ts"

export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  const uuid = ref.match(/([0-9a-f]{32})\/?$/i)?.[1]
  if (!uuid) throw new CliError(`cannot read ${ref}: pass a MyCareersFuture job uuid or job URL`, "INVALID_VALUE")
  const body = await getJson<Record<string, unknown>>(`${apiBase()}/v2/jobs/${uuid}`, { label: "MyCareersFuture API", ua: UA })
  return body ? mcfToJob(body) : null
}
