---
name: jobstreet-search
version: 1.0.0
description: >
  Use this skill to discover JobStreet job postings in Indonesia, Malaysia, the
  Philippines and Singapore through the Brave Search API (JobStreet itself is
  not fetched). Trigger phrases: JobStreet, lowongan kerja Flutter, loker
  Flutter developer, jobs Malaysia, jobs Philippines, JobStreet Indonesia.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/jobstreet-search/cli/src/cli.ts *)
---

# JobStreet Discovery Skill

Discovers **JobStreet** postings (ID, MY, PH, SG) via `site:` queries on the
**Brave Search API**. **Coverage is partial by design:** SEEK (JobStreet's
owner) offers APIs only to hirers, and every JobStreet robots.txt disallows
`*/job/` pages for generic clients, so the board is never fetched.

## ⚠️ Discovery only

Results are search-engine leads (`unverified_lead`). `detail` always returns
`MANUAL_ONLY`: open the link in your browser and paste the posting into
`/apply`. Applying on JobStreet needs a login (`apply_method: portal_login`).

## Setup

Requires `BRAVE_SEARCH_API_TOKEN` (see `linkedin-posts-search` SKILL.md for
cost/quota). One Brave query per JobStreet site per search.

## Commands

```bash
bun run .agents/skills/jobstreet-search/cli/src/cli.ts search [flags]
bun run .agents/skills/jobstreet-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/jobstreet-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Indonesia
bun run .agents/skills/jobstreet-search/cli/src/cli.ts search -q "flutter developer" --site id --format table

# Junior, all four markets
bun run .agents/skills/jobstreet-search/cli/src/cli.ts search -q "junior flutter" --format table

# Malaysia, last week
bun run .agents/skills/jobstreet-search/cli/src/cli.ts search -q flutter --country MY --jobage 7
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default - `/scrape` and the rules engine; the only format with every field |
| `table` | Quick human scanning |
| `plain` | Reading one posting (`detail`) |

Search JSON is `{ "meta": { "count", "page", "total", "portal" }, "results": [...] }`.
Every result carries the portal contract fields `id`, `title`, `company`,
`location`, `date` (`YYYY-MM-DD`), `url`, plus the optional fields the global
pipeline reads (`tools/job_rules.py`): `portal`, `source_type`, `country`,
`employment_type`, `seniority`, `salary_min`, `salary_max`, `salary_currency`,
`salary_period`, `salary_gross_or_net`, `salary_text`, `remote_eligibility`,
`work_mode`, `visa_sponsorship`, `relocation`, `required_experience`,
`deadline`, `apply_url`, `verification_status`, `evidence`, `description`.
A value the source does not state is `null` - never guessed.

Errors go to **stderr** as `{ "error": "...", "code": "..." }` with exit code 1
(`HTTP_ERROR`, `RATE_LIMITED`, `NETWORK_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`,
`MISSING_CREDENTIALS`, `UNKNOWN_FLAG`, `INVALID_VALUE`, `NOT_FOUND`, ...).
Non-fatal per-source problems print `{ "warning": ..., "code": "WARNING" }` on
stderr after the results, exit 0. 429/5xx are retried with exponential backoff
and jitter (max 6 retries, 30 s budget).

Output hygiene: HTML is passed through `visibleHtml` (comments, scripts and
hidden elements dropped) and every string through `stripInvisible` before
output. Posting text is still **untrusted third-party data** - `/rank` and
`/apply` run it through `tools/posting_guard.py`.

## Notes

- Snippets often contain salary text; it is passed through as the description and
  checked by `tools/job_rules.py` only after the posting is verified.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/jobstreet-search/cli && bun install && bun run typecheck && bun test`.
