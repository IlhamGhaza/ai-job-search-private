import { CliError, type Opts } from "../helpers.ts"
import { manualOnly, postJson, type Gig } from "../gig.ts"
import { DETAIL_QUERY, PLATFORM, UA, graphqlUrl, parseNode, upworkToken, type UpworkNode } from "./search.ts"

/** The posting id from a ref: a numeric id, or ~0<digits> in an Upwork job URL. */
export function upworkId(ref: string): string | null {
  // A hex ciphertext (~01ab...) is not the numeric id the API takes: use the gig_id from search output instead.
  const m = ref.match(/~0?(\d{6,})(?![0-9a-z])/i) ?? ref.match(/^(\d{6,})$/)
  return m ? m[1] : null
}

/** One posting through the GraphQL API. Without a token the page is never fetched: MANUAL_ONLY. */
export async function runDetail(ref: string, _opts: Opts): Promise<Gig | null> {
  const token = upworkToken()
  if (!token) return manualOnly(PLATFORM, ref)
  const id = upworkId(ref)
  if (!id) throw new CliError(`no Upwork posting id in ${ref}; pass the id or a job URL containing ~0<id>`, "INVALID_VALUE")
  const body = await postJson<{ data?: { marketplaceJobPosting?: UpworkNode | null }; errors?: Array<{ message?: string }> }>(
    graphqlUrl(),
    { query: DETAIL_QUERY, variables: { id } },
    { label: "Upwork GraphQL API", ua: UA, headers: { Authorization: `Bearer ${token}` } },
  )
  if (body?.errors?.length) throw new CliError(`Upwork GraphQL API: ${body.errors.map((e) => e.message).join("; ").slice(0, 300)}`, "BAD_RESPONSE")
  const node = body?.data?.marketplaceJobPosting
  return node ? parseNode(node) : null
}
