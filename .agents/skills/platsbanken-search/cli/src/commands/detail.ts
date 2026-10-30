import { CliError, getJson, type Job, type Opts } from "../helpers.ts"
import { apiBase, headers, hitToJob, UA } from "./search.ts"

export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  const id = ref.match(/(\d{6,})\/?$/)?.[1]
  if (!id) throw new CliError(`cannot read ${ref}: pass a Platsbanken ad id or annons URL`, "INVALID_VALUE")
  const ad = await getJson<Record<string, unknown>>(`${apiBase()}/ad/${id}`, { label: "JobTech JobSearch API", ua: UA, headers: headers() })
  if (!ad || ad.removed === true) return null
  return hitToJob(ad)
}
