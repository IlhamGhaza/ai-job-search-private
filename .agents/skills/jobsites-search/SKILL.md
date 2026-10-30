---
name: jobsites-search
version: 1.0.0
description: >
  Use this skill to discover postings on regional job boards that have no
  permitted job-seeker API - Glints, Kalibrr, Dealls, KitaLulus, Tech in Asia,
  Hiredly, JobsDB, JobThai, ITviec, TopDev, VietnamWorks, NodeFlair, TokyoDev,
  Japan Dev, GaijinPot, Wanted, Saramin, Jumpit, SEEK, Jora, Trade Me, Welcome
  to the Jungle, Reed, CWJobs, IrishJobs, StepStone, Berlin Startup Jobs,
  GermanTechJobs, karriere.at, jobs.ch, SwissDevJobs, Werk.nl, VDAB, Moovijob,
  The Hub, Duunitori, FINN, Alfred, Wellfound, Built In, Dice, Indeed, Job Bank
  Canada, and the global remote boards JustRemote, Remotely.jobs, PowerToFly
  and Job-Hunt.org - through the Brave Search API. Trigger phrases: lowongan kerja,
  loker, jobs in Vietnam, jobs in Japan, jobs in Korea, jobs in Australia,
  regional job boards.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/jobsites-search/cli/src/cli.ts *)
---

# Regional Job-Boards Discovery Skill

Discovers postings on ~45 regional boards via `site:` queries on the **Brave
Search API**. The boards are **never crawled**. `detail` reads one posting page
(schema.org JSON-LD only) **only** when the board is marked `fetchable` in
`cli/src/sites.ts` **and** its robots.txt allows the path at call time;
otherwise it returns `MANUAL_ONLY` - open the link and paste into `/apply`.

## ⚠️ Personal use; discovery first

`fetchable: true` means robots.txt allowed posting pages when checked
(2026-10-30) and the board is not a large commercial portal known to restrict
automated access. Board terms were **not** reviewed one by one: if you find a
board's terms forbid automated reads, set its `fetchable` to `false`. Big
commercial boards (SEEK, Indeed, Glints, StepStone group, Wellfound, Dice,
Wanted, Saramin, FINN, ...) are discovery-only.

## Setup

Requires `BRAVE_SEARCH_API_TOKEN` (see `linkedin-posts-search` SKILL.md for
cost/quota). One Brave query per board; `--max-sites` caps a run (default 5).

## Commands

```bash
bun run .agents/skills/jobsites-search/cli/src/cli.ts search [flags]
bun run .agents/skills/jobsites-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/jobsites-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Indonesia boards (default)
bun run .agents/skills/jobsites-search/cli/src/cli.ts search -q "flutter developer" --format table

# Vietnam
bun run .agents/skills/jobsites-search/cli/src/cli.ts search -q "flutter" --country VN --format table

# Japan English-friendly boards
bun run .agents/skills/jobsites-search/cli/src/cli.ts search -q "flutter" --site tokyodev,japandev --format table

# Global remote boards (JustRemote, Remotely.jobs, PowerToFly, Job-Hunt.org)
bun run .agents/skills/jobsites-search/cli/src/cli.ts search -q "flutter" --country GLOBAL --format table

# Germany startups
bun run .agents/skills/jobsites-search/cli/src/cli.ts search -q flutter --site berlinstartupjobs,germantechjobs

# Read one fetchable posting
bun run .agents/skills/jobsites-search/cli/src/cli.ts detail https://www.tokyodev.com/companies/acme/jobs/flutter-engineer --format plain
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

- `bun run src/cli.ts --help` prints every board key, country and detail mode.
- Saramin has an official API but it requires an approved key; not wired (discovery only).
- Multi-country boards (Kalibrr, Tech in Asia, The Hub) leave `country` null on leads.
- Global remote boards without an API or feed (JustRemote, Remotely.jobs, PowerToFly,
  Job-Hunt.org) are selected with `--country GLOBAL`. Remote OK has its own CLI
  (`remoteok-search`). PowerToFly applications need an account (`apply_method: portal_login`).
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/jobsites-search/cli && bun install && bun run typecheck && bun test`.
