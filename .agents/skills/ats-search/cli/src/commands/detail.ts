import { CliError, type Job, type Opts } from "../helpers.ts"
import { fetchOne, parseJobRef } from "../providers.ts"

export async function runDetail(ref: string, _opts: Opts): Promise<Job | null> {
  const parsed = parseJobRef(ref)
  if (!parsed) {
    throw new CliError(
      `cannot read ${ref}: pass a search result id (<ats>:<board>:<id>) or a Greenhouse/Lever/Ashby/Workable/Recruitee posting URL`,
      "INVALID_VALUE",
    )
  }
  return fetchOne(parsed.ats, parsed.board, parsed.id, parsed.board)
}
