---
name: remotive-search
version: 1.0.0
description: >
  Use this skill to search remote software jobs on Remotive through its public
  API, including each job's candidate location eligibility. Trigger phrases:
  Remotive jobs, remote developer jobs, remote Flutter jobs, worldwide remote
  roles.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/remotive-search/cli/src/cli.ts *)
---

# Remotive Search Skill

Searches **[Remotive](https://remotive.com)** through its public remote-jobs API.
Every job carries `candidate_required_location`, stored as `remote_eligibility`
so the rules engine can tell "Worldwide" from "USA only".

## Terms of use (read before running)

Remotive's API notice: link back to the Remotive job URL and name Remotive as
the source; don't resubmit jobs to other job sites; **call the API at most ~4
times a day** (data changes slowly and jobs are delayed 24 h). Each `search`
or `detail` is one call. Remotive offers a paid private API for heavier use.

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/remotive-search/cli/src/cli.ts search [flags]
bun run .agents/skills/remotive-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/remotive-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter jobs
bun run .agents/skills/remotive-search/cli/src/cli.ts search -q flutter --format table

# Mobile roles open to Asia
bun run .agents/skills/remotive-search/cli/src/cli.ts search -q "flutter OR mobile" -l "asia OR worldwide OR anywhere" --format table

# Last week only
bun run .agents/skills/remotive-search/cli/src/cli.ts search -q flutter --jobage 7

# One job by id
bun run .agents/skills/remotive-search/cli/src/cli.ts detail 2091135 --format plain
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

- `--query` without `OR` is sent as Remotive's `search` and then re-matched
  client-side; an `OR` query reads the whole category and matches locally.
- Salary is free text in the API: kept as `salary_text`, never parsed into numbers here
  (`tools/job_rules.py` decides whether its currency and period are clear).
- No per-job endpoint: `detail` re-reads the category (counts toward the daily budget).
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/remotive-search/cli && bun install && bun run typecheck && bun test`.
