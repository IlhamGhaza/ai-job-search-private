---
name: himalayas-search
version: 1.0.0
description: >
  Use this skill to search remote jobs on Himalayas through its public API,
  including the countries each job accepts applicants from. Trigger phrases:
  Himalayas jobs, remote jobs open to Indonesia, remote Flutter jobs,
  location-restricted remote roles.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/himalayas-search/cli/src/cli.ts *)
---

# Himalayas Search Skill

Searches **[Himalayas](https://himalayas.app)** through its public search API.
Each job lists `locationRestrictions` (countries it accepts) and
`timezoneRestrictions`, so geographic eligibility is captured, not assumed.

## Terms of use

Himalayas' API is public; credit Himalayas and link to its job URL when
sharing results. Its robots.txt disallows paging search results
(`/jobs*&page=`), so this CLI fetches **page 1 only** - narrow the query instead.

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/himalayas-search/cli/src/cli.ts search [flags]
bun run .agents/skills/himalayas-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/himalayas-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter, open to Indonesia
bun run .agents/skills/himalayas-search/cli/src/cli.ts search -q flutter --country ID --format table

# Worldwide-open roles
bun run .agents/skills/himalayas-search/cli/src/cli.ts search -q flutter --worldwide --format table

# Junior titles only
bun run .agents/skills/himalayas-search/cli/src/cli.ts search -q flutter --title-query "junior OR entry OR graduate OR associate"

# Posting detail
bun run .agents/skills/himalayas-search/cli/src/cli.ts detail https://himalayas.app/companies/acme/jobs/junior-flutter --format plain
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

- An empty `locationRestrictions` list is recorded as `"no location restriction listed"`,
  not as "accepts Indonesia": the rules engine treats it as unconfirmed.
- `--country` is Himalayas' own eligibility filter (ISO code or name).
- `detail` tries the job page's schema.org JSON-LD after a robots.txt check, but Himalayas answered **403 to non-browser clients** when checked (2026-10-30), so `detail` usually exits `FORBIDDEN`. This is not worked around: every search result already carries the full `description`.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/himalayas-search/cli && bun install && bun run typecheck && bun test`.
