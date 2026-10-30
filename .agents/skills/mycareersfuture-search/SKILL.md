---
name: mycareersfuture-search
version: 1.0.0
description: >
  Use this skill to search Singapore jobs on MyCareersFuture, the Singapore
  government's job portal, with salary ranges. Trigger phrases: jobs in
  Singapore, MyCareersFuture, MCF jobs, Flutter Singapore, mobile developer
  Singapore.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts *)
---

# MyCareersFuture (Singapore) Search Skill

Searches **[MyCareersFuture](https://www.mycareersfuture.gov.sg)** (Workforce
Singapore) through the JSON API its own web app calls. Singapore law requires
most postings here to show a salary range, so `salary_*` is usually filled.

## ⚠️ Personal use only

The API is public (no key) but **undocumented** - it is the site's own
backend, not a published developer API. robots.txt permits all paths for
generic clients. Keep volume low (a few searches per run), personal use only.
If the site changes or objects, set `enabled: false`.

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts search [flags]
bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter
bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts search -q flutter --format table

# Mobile app developer, last 14 days
bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts search -q "mobile app developer" --jobage 14 --format table

# Detail
bun run .agents/skills/mycareersfuture-search/cli/src/cli.ts detail cacb464bcc98690b05b0c196bc5a21df --format plain
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

- Salary is gross SGD as posted (`salary_period` from MCF's salary type, usually month).
- `minimumYearsExperience` -> `required_experience`; `positionLevels` -> `seniority`.
- Work-pass eligibility (Employment Pass / S Pass) is not stated in postings: treat as unknown.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/mycareersfuture-search/cli && bun install && bun run typecheck && bun test`.
