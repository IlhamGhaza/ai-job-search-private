---
name: platsbanken-search
version: 1.0.0
description: >
  Use this skill to search Swedish job ads in Platsbanken (Arbetsförmedlingen)
  through JobTech's open JobSearch API. Trigger phrases: jobs in Sweden,
  Platsbanken, Arbetsförmedlingen, lediga jobb, utvecklare jobb, Flutter
  Sverige.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/platsbanken-search/cli/src/cli.ts *)
---

# Platsbanken (JobTech) Search Skill

Searches **Platsbanken** (Sweden's public employment service) through
**JobTech's open JobSearch API** - open data published for exactly this use.

## Setup

No credentials needed. `JOBTECH_API_TOKEN` is optional; when set it is sent as
the `api-key` header (JobTech issues free keys at https://apirequest.jobtechdev.se).

## Commands

```bash
bun run .agents/skills/platsbanken-search/cli/src/cli.ts search [flags]
bun run .agents/skills/platsbanken-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/platsbanken-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter
bun run .agents/skills/platsbanken-search/cli/src/cli.ts search -q flutter --format table

# App developers, last 14 days
bun run .agents/skills/platsbanken-search/cli/src/cli.ts search -q apputvecklare --jobage 14 --format table

# Remote
bun run .agents/skills/platsbanken-search/cli/src/cli.ts search -q utvecklare --remote

# Ad detail
bun run .agents/skills/platsbanken-search/cli/src/cli.ts detail 31635810 --format plain
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

- Words in `--query` are ANDed server-side; `OR` is dropped (run separate queries).
- Salary arrives as text (`salary_type` label + `salary_description`) and is kept as `salary_text`.
- Most ads are in Swedish; the Language Gate applies to Swedish-required roles.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/platsbanken-search/cli && bun install && bun run typecheck && bun test`.
