---
name: remoteok-search
version: 1.0.0
description: >
  Use this skill to search remote jobs on Remote OK through its public JSON API.
  Trigger phrases: Remote OK jobs, remoteok, remote Flutter jobs, remote mobile
  developer jobs.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/remoteok-search/cli/src/cli.ts *)
---

# Remote OK Search Skill

Searches **[Remote OK](https://remoteok.com)** through its public JSON API (`/api`).

## Terms of use

Remote OK's API terms: link back to the Remote OK job URL (no `nofollow`) and
mention Remote OK as the source, or API access may be suspended. Don't use
their logo. robots.txt content signals: `search=yes, ai-train=no,
use=reference` - this skill only reads listings for your own job search.

## Setup

No credentials.

## Commands

```bash
bun run .agents/skills/remoteok-search/cli/src/cli.ts search [flags]
bun run .agents/skills/remoteok-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/remoteok-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter tag
bun run .agents/skills/remoteok-search/cli/src/cli.ts search --tag flutter --format table

# Mobile tag, keyword filter
bun run .agents/skills/remoteok-search/cli/src/cli.ts search --tag mobile -q "flutter OR dart" --format table

# Worldwide only
bun run .agents/skills/remoteok-search/cli/src/cli.ts search --tag flutter -l "worldwide OR anywhere"

# One job
bun run .agents/skills/remoteok-search/cli/src/cli.ts detail 1137531 --format plain
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

- The first array element is a legal notice and is skipped.
- Salary, when non-zero, is **USD per year** (Remote OK's convention); `0` means not stated.
- `--tag` takes one tag; other filtering is client-side.
- No per-job endpoint: `detail` re-reads the feed.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/remoteok-search/cli && bun install && bun run typecheck && bun test`.
