---
name: weworkremotely-search
version: 1.0.0
description: >
  Use this skill to search remote jobs on We Work Remotely through its public
  RSS feeds, with each job's region eligibility. Trigger phrases: We Work
  Remotely, WWR jobs, remote programming jobs, remote jobs anywhere in the
  world.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/weworkremotely-search/cli/src/cli.ts *)
---

# We Work Remotely Search Skill

Reads **[We Work Remotely](https://weworkremotely.com)**'s public RSS feeds (one
request per search). Each item's `<region>` (e.g. "Anywhere in the World",
"USA Only") becomes `remote_eligibility`.

## Terms of use

Public RSS feeds; link back to the WWR listing when sharing. robots.txt allows
everything except account/admin paths.

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search [flags]
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Mobile/Flutter in programming feed
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q "flutter OR mobile OR ios OR android" --format table

# Anywhere-in-the-world only
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search -q flutter -l "anywhere" --format table

# All categories
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts search --category all -q flutter

# Detail
bun run .agents/skills/weworkremotely-search/cli/src/cli.ts detail https://weworkremotely.com/remote-jobs/acme-junior-flutter-developer --format plain
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

- RSS titles are `Company: Role`; split into `company` and `title`.
- The `Headquarters:` line in the description is kept as evidence, not as the job location.
- `detail` prefers the job page's JSON-LD (robots-checked) and falls back to the RSS item.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/weworkremotely-search/cli && bun install && bun run typecheck && bun test`.
