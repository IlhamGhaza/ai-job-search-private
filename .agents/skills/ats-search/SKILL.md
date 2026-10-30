---
name: ats-search
version: 1.0.0
description: >
  Use this skill to search company career pages through the official public
  job-board APIs of Greenhouse, Lever, Ashby, Workable and Recruitee, for a
  configurable list of companies (companies.json beside this file). Covers
  employers that hire Flutter / mobile engineers directly. Trigger phrases:
  company career pages, search Greenhouse jobs, Lever jobs, Ashby jobs, jobs at
  <company>, employer job board, ATS search.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/ats-search/cli/src/cli.ts *)
---

# ATS Career-Board Search Skill

Searches **company career boards** through the ATS vendors' own public
job-board APIs - the endpoints the vendors document for embedding a company's
openings on its website. No API key, no HTML scraping, zero runtime
dependencies. The company list is the plain JSON file
[`companies.json`](companies.json): add `{ "name", "ats", "board" }` objects to
cover more employers.

## Setup

No credentials. Edit `companies.json` to choose companies:

```json
{ "name": "Acme", "ats": "greenhouse", "board": "acme" }
```

`board` is the slug in the company's board URL: `boards.greenhouse.io/<board>`,
`jobs.lever.co/<board>`, `jobs.ashbyhq.com/<board>`,
`apply.workable.com/<board>`, `<board>.recruitee.com`. The seed list was
verified on 2026-10-30; entries without a supported board or without openings
are recorded under `dropped` with the reason.

## Commands

```bash
bun run .agents/skills/ats-search/cli/src/cli.ts search [flags]
bun run .agents/skills/ats-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/ats-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Flutter/Dart roles at every listed company
bun run .agents/skills/ats-search/cli/src/cli.ts search -q "flutter OR dart" --format table

# Mobile titles, remote only, last 14 days
bun run .agents/skills/ats-search/cli/src/cli.ts search --title-query "flutter OR mobile OR android OR ios" -l "remote" --jobage 14 --format table

# One company only
bun run .agents/skills/ats-search/cli/src/cli.ts search --company canonical --title-query "engineer" --format table

# Only Greenhouse boards
bun run .agents/skills/ats-search/cli/src/cli.ts search --ats greenhouse -q "junior" --no-description

# Full posting
bun run .agents/skills/ats-search/cli/src/cli.ts detail greenhouse:canonical:8318647 --format plain

# From a posting URL
bun run .agents/skills/ats-search/cli/src/cli.ts detail https://jobs.lever.co/acme/abc-123 --format plain
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

- Keyword filtering is **client-side** (the board APIs return a company's whole
  board): `a b` = all words, `"a b"` = phrase, `a OR b` = either.
- One failing board is a stderr warning, not a failed run.
- **SmartRecruiters is not supported**: `api.smartrecruiters.com/robots.txt`
  disallows every generic client (`User-agent: * / Disallow: /`).
- **Workday and in-house career sites** (BMW, Toyota, Google) have no public
  job-board API and are out of scope; add their postings by URL to `/apply`.
- Posting URLs land on official ATS hosts, which `/apply` already treats as
  verified employer sources.
- Ashby and Workable have no per-job endpoint, so `detail` re-reads that board.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/ats-search/cli && bun install && bun run typecheck && bun test`.
