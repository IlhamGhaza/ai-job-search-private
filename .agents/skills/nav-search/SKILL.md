---
name: nav-search
version: 1.0.0
description: >
  Use this skill to search Norwegian job ads from NAV / arbeidsplassen.no
  through NAV's public job vacancy feed. Trigger phrases: jobs in Norway,
  arbeidsplassen, NAV stillinger, ledige stillinger, utvikler jobb, Flutter
  Norge.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/nav-search/cli/src/cli.ts *)
---

# NAV (Norway) Search Skill

Reads **NAV's public job vacancy feed** (`pam-stilling-feed`, the official feed
behind arbeidsplassen.no). The feed has no keyword search: the CLI reads feed
pages changed within `--jobage` days, matches titles/employers locally, and
fetches full ads only for matches.

## Setup

No sign-up needed: the CLI uses the public token NAV publishes at
`/api/publicToken`. To use your own consumer token instead, export
`NAV_API_TOKEN`.

## Commands

```bash
bun run .agents/skills/nav-search/cli/src/cli.ts search [flags]
bun run .agents/skills/nav-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/nav-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Developers (compound words match)
bun run .agents/skills/nav-search/cli/src/cli.ts search -q "utvikler OR developer" --jobage 3 --format table

# Flutter / app
bun run .agents/skills/nav-search/cli/src/cli.ts search -q "flutter OR apputvikler OR mobilutvikler" --jobage 7

# More feed pages
bun run .agents/skills/nav-search/cli/src/cli.ts search -q flutter --jobage 14 --max-pages 10

# Ad detail
bun run .agents/skills/nav-search/cli/src/cli.ts detail fc12155d-04fd-4887-92cb-011ed541f443 --format plain
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

- Matching is **substring** (Norwegian compounds: `utvikler` matches `Systemutvikler`).
- Each feed page holds 1000 entries, oldest change first from the `If-Modified-Since` date;
  raise `--max-pages` for long windows.
- Contact persons in ads are deliberately not copied into the output.
- Ads are mostly Norwegian; the Language Gate applies.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/nav-search/cli && bun install && bun run typecheck && bun test`.
