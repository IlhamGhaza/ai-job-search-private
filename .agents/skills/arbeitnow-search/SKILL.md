---
name: arbeitnow-search
version: 1.0.0
description: >
  Use this skill to search Germany / EU jobs on Arbeitnow through its free public
  job-board API, including its visa-sponsorship and remote filters. Trigger
  phrases: Arbeitnow, jobs in Germany, visa sponsorship Germany, English-speaking
  jobs Berlin, Stellenangebote Entwickler, Jobs mit Visum.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/arbeitnow-search/cli/src/cli.ts *)
---

# Arbeitnow Search Skill

Searches **[Arbeitnow](https://www.arbeitnow.com)** (Germany/EU, many English-language
roles) through its free public job-board API.

## Terms of use

"This is a free public API for jobs, please do not abuse. I would appreciate
linking back to the site." Keep `--max-pages` low (each page = 300 jobs).

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search [flags]
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter/mobile, visa filter
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search -q "flutter OR mobile OR ios OR android" --visa --format table

# Remote only
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search -q flutter --remote --format table

# Berlin
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search -q "flutter OR dart" -l Berlin

# Detail
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts detail https://www.arbeitnow.com/jobs/companies/acme/flutter-developer-123 --format plain
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

- **Visa flag caveat:** the API accepts `visa_sponsorship=true` but its response
  carries **no per-job visa field**. With `--visa`, results are tagged
  `visa_sponsorship: "tagged by Arbeitnow's visa-sponsorship filter (unconfirmed by employer text)"`.
  The rules engine treats this as evidence to verify, never as proof.
- No keyword search server-side: up to `--max-pages` pages (default 2) are read
  newest-first and filtered locally; paging stops early once older than `--jobage`.
- Many listings are German-language: the Language Gate in `04-job-evaluation.md` applies.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/arbeitnow-search/cli && bun install && bun run typecheck && bun test`.
