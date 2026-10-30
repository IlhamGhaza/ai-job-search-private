---
name: linkedin-posts-search
version: 1.0.0
description: >
  Use this skill to discover public LinkedIn hiring posts (not job listings)
  through the Brave Search API, e.g. people posting "we're hiring a junior
  Flutter developer". Trigger phrases: LinkedIn hiring posts, LinkedIn posts
  hiring Flutter, social hiring posts, recruiter posts.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts *)
---

# LinkedIn Hiring-Posts Search Skill

Finds **public LinkedIn posts** that mention hiring, through the **Brave Search
API** (`site:linkedin.com/posts ...`). LinkedIn itself is **never fetched,
crawled or logged into**. Every result is `source_type: social_post`,
`verification_status: unverified_lead`, with the post URL, the search snippet,
the query and `discovered_at`. A snippet is **not** a verified job: find the
real listing (employer site / ATS) before `/apply`.

## ⚠️ Personal use; leads only

Search-engine snippets of public posts. No authenticated feed scraping, no
cookie reuse. Check your Brave plan's terms on storing results; this skill
stores only the URL, snippet and query in your local `seen_jobs.json`.

## Setup

**Credential required.** Get a Brave Search API key at
https://brave.com/search/api/ and export it (never commit it, never pass it as a flag):

```bash
export BRAVE_SEARCH_API_TOKEN=...      # PowerShell: $env:BRAVE_SEARCH_API_TOKEN="..."
```

**Cost/quota:** every `search`/`detail` is one Brave query. Brave's plans and
free allowance change - check the current pricing page before use (at the time
of writing, plans were metered per 1,000 queries with a rate limit of about
1 query/second on the entry tier). `/scrape` runs ~3-6 queries per run with this skill.

## Commands

```bash
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts search [flags]
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts detail <id|url> [--format json|plain]
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts --help      # every flag, with defaults
```

Common search flags (all portals in this repo): `--query/-q`, `--jobage <days>`,
`--page <n>` (1-indexed), `--limit/-n <n>`, `--format json|table|plain`.
Portal-specific flags are listed by `--help` and in the examples below.

## Examples

```bash
# Junior Flutter hiring posts
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts search -q "\"junior flutter\"" --format table

# Singapore, last week
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts search -q "flutter developer" -l Singapore --jobage 7

# Indonesia
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts search -q "lowongan flutter developer" -l Indonesia

# Refresh one post's snippet
bun run .agents/skills/linkedin-posts-search/cli/src/cli.ts detail https://www.linkedin.com/posts/janedoe_hiring-flutter-activity-1
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

- `company` stays `null`: the poster (`poster`) may be a recruiter or a person, not the employer.
- `/scrape` should try to link each lead to a real listing (dedup step) and prefer that listing.
- The existing `linkedin-search` (guest job listings) is unchanged.
- Data source and parsing anchors: [url-reference.md](url-reference.md).
- Offline tests: `cd .agents/skills/linkedin-posts-search/cli && bun install && bun run typecheck && bun test`.
