---
name: jobicy-search
version: 1.0.0
description: >
  Use this skill to search remote jobs on Jobicy through its public API with
  region (geo) filters. Trigger phrases: Jobicy jobs, remote jobs in APAC,
  remote Flutter jobs, remote developer jobs Asia.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/jobicy-search/cli/src/cli.ts *)
---

# Jobicy Search Skill

Searches **[Jobicy](https://jobicy.com)** through its public remote-jobs API (v2).

## Terms of use

Jobicy asks API users to credit Jobicy with a direct link to the source listing
and not to poll more often than about once an hour.

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/jobicy-search/cli/src/cli.ts search [flags]
bun run .agents/skills/jobicy-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/jobicy-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter, APAC
bun run .agents/skills/jobicy-search/cli/src/cli.ts search --tag flutter --geo apac --format table

# Dev industry, anywhere
bun run .agents/skills/jobicy-search/cli/src/cli.ts search --industry dev --geo anywhere -q "flutter OR mobile"

# Detail
bun run .agents/skills/jobicy-search/cli/src/cli.ts detail https://jobicy.com/jobs/157192-flutter-developer --format plain
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

- `jobGeo` (e.g. `APAC`, `USA`, `Anywhere`) is stored as `remote_eligibility`.
- `--tag` is loose server-side; the client-side `-q` filter tightens it.
- `detail` reads the job page's JSON-LD after a robots.txt check.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/jobicy-search/cli && bun install && bun run typecheck && bun test`.
