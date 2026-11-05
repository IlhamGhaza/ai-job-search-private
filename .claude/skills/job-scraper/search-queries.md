# Search Queries for Job Scraper

<!-- SETUP: Customize these queries based on your skills, target roles, and location -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. Shipped country-agnostic CLIs include `linkedin-search` and `freehire-search`; Danish demos and any skill you add with `/add-portal` are included the same way. You do **not** need a matching `site:` line below for those CLIs to run.

The `site:` query templates in this file are the **WebSearch fallback** — for portals without a CLI, company career pages, or when a CLI fails.

**Language scope:** write every query category in every language listed in your CLAUDE.md Languages table (typically 1-2, sometimes more). A posting requiring a language you have *not* declared, as a job condition, is excluded before scoring; a posting requiring a *higher level* than you declared in a language you *do* work in is flagged for your own judgment, not excluded — see `04-job-evaluation.md`'s Language Gate, the single source of truth for this rule. Translate each category's keywords rather than machine-translating word-for-word (e.g. "Frontend Developer" -> "Desarrollador Frontend", not a literal word-for-word translation) if you work in more than one language.

## Search Sites

Primary (default CLIs, remote/international focus - no local Indonesian portal scaffolded; run `/add-portal` to add one):
- **linkedin.com/jobs** - LinkedIn job listings, global; also covered by `linkedin-search` CLI
- **freehire.com** - also covered by `freehire-search` CLI
- **remoteok.com**, **weworkremotely.com**, **himalayas.app** - remote-first job boards (WebSearch fallback, no CLI)
- **whatjobs.com** (en-id.whatjobs.com for Indonesia) - job aggregator, surfaced real Flutter roles in Tangerang (WebSearch fallback, e.g. `site:whatjobs.com flutter developer`)
- **angel.co / wellfound.com** - startup roles, often remote-friendly with visa sponsorship notes

Secondary (company career pages via Google):
- Direct Google searches with `site:` filters for known target companies

## Global Junior Flutter Search (CLI portals)

Target, accept/reject rules and the hard rules live in `04-job-evaluation.md` ("Global Junior Flutter Search - Hard Rules"). This section only says **what to ask each portal**. Searches are global; the priority countries below steer *where to look first* and how `/rank` orders results - they never exclude a job.

**Priority countries:** the `relocation_countries` in `tools/data/salary_benchmarks.json` plus Indonesia (`python3 tools/job_rules.py benchmarks` lists them). The same list decides where onsite work is allowed, so search and relocation cannot drift apart.

**Title vocabulary** (combine with `OR` where the portal supports it):
`junior flutter`, `flutter developer`, `flutter engineer`, `junior dart`, `junior mobile developer`, `junior mobile engineer`, `cross-platform developer`, `associate mobile engineer`, `graduate mobile engineer`, `entry level flutter`.
Local terms: `lowongan flutter developer`, `loker flutter` (ID); `flutterutvecklare`, `apputvecklare`, `mobilutvecklare` (SE); `flutter-utvikler`, `apputvikler`, `mobilutvikler` (NO); `Flutter Entwickler` (DE); `Flutter 엔지니어` (KR); `Flutter エンジニア` (JP).

| Portal CLI | Default run (scope to 14 days with each portal's recency flag) |
|---|---|
| `ats-search` | `search --title-query "flutter OR dart OR mobile OR android OR ios" --jobage 14` |
| `remotive-search` | `search -q flutter` (max ~4 calls/day - one per run) |
| `remoteok-search` | `search --tag flutter --jobage 14` |
| `himalayas-search` | `search -q flutter --country ID` and `search -q flutter --worldwide` |
| `jobicy-search` | `search --tag flutter --geo apac` and `--geo anywhere` |
| `weworkremotely-search` | `search -q "flutter OR dart OR mobile" --jobage 14` |
| `arbeitnow-search` | `search -q "flutter OR dart OR mobile" --visa --jobage 14` |
| `platsbanken-search` | `search -q flutter --jobage 14`, `search -q apputvecklare --jobage 14` |
| `nav-search` | `search -q "flutter OR apputvikler OR mobilutvikler" --jobage 7` |
| `mycareersfuture-search` | `search -q flutter --jobage 14` |
| `freehire-search` | `search -q "flutter OR dart" --seniority junior --jobage 14`, then per priority country `--country SG,MY,PH,TH,VN,ID` / `--country DE,NL,GB,IE` / `--country US,CA,AU,NZ,JP,KR` and `--remote remote` |
| `linkedin-search` | `search -q "junior flutter developer" -l "<place>" --jobage 14` for `-l` in: Indonesia, Singapore, Malaysia, Philippines, Thailand, Vietnam, Japan, South Korea, Australia, New Zealand, Germany, Netherlands, United Kingdom, Ireland, Canada, United States, Remote |
| `linkedin-posts-search` | `search -q "\"junior flutter\"" --jobage 7`; `search -q "flutter developer" -l Indonesia --jobage 7` (leads only; needs `BRAVE_SEARCH_API_TOKEN`) |
| `jobstreet-search` | `search -q "flutter developer" --jobage 14` (all four markets; leads only; needs the Brave token) |
| `jobsites-search` | `search -q "flutter developer" --country <code> --jobage 14` rotating ID, VN, JP, KR, AU, DE, NL, and `--country GLOBAL` for JustRemote, Remotely.jobs, PowerToFly, Job-Hunt.org (5 boards max per call; needs the Brave token) |

The Danish demo portals (`jobindex-search`, `jobnet-search`, `jobbank-search`, `jobdanmark-search`) rarely list junior Flutter roles; leave them enabled or set `enabled: false` in their `SKILL.md` - your choice.

## Query Categories

Queries are grouped by priority. Write **each category in every language from your Languages table** (see Language scope above). Combine each query with your location terms (e.g. your city, region, or metro area) where the site supports it.

**Organize by function, not job title.** The same underlying work carries different titles across companies and markets (a "Data Scientist" role at one employer may be posted as "Insights Analyst" or "Data Consultant" at another). Name each priority category after the function it covers, and list several plausible job titles as query variants within that category rather than betting an entire priority tier on one exact title string.

### Priority 1: Flutter / Mobile Developer

These match your strongest and most desired career direction.

```
site:linkedin.com/jobs "Flutter Developer" remote
site:linkedin.com/jobs "Mobile Developer" remote
site:linkedin.com/jobs "Mobile App Developer" remote
"Flutter Developer" remote OR "visa sponsorship" OR "relocation"
```

### Priority 2: Mobile Domain Expertise

These match your domain expertise (HRIS, fleet, POS, inventory, IoT, food ordering apps).

```
"Flutter Developer" BLoC OR GetX OR "Clean Architecture" remote
"Mobile Developer" Firebase OR MQTT OR "REST API" remote
site:linkedin.com/jobs "Flutter" "Clean Architecture" remote
```

### Priority 3: Broader Software Engineer (pivot-adjacent)

Adjacent roles you could pivot into.

```
site:linkedin.com/jobs "Software Engineer" Flutter remote
site:linkedin.com/jobs "Junior Software Engineer" mobile remote
"Full Stack Developer" Flutter OR Dart remote
```

### Priority 4: Broader Technical / Startup

Wider net for general technical roles at remote-friendly or visa-sponsoring companies.

```
site:linkedin.com/jobs "Mobile Developer" "visa sponsorship"
site:wellfound.com Flutter developer remote
"Mobile Developer" startup remote "open to relocation"
```

## Location Filter

Preference is remote-first; relocation is acceptable only within the relocation countries in `tools/data/salary_benchmarks.json`. `tools/job_rules.py` enforces this; the filter below describes it:
- **Ideal:** Fully remote, worldwide or Indonesia-inclusive
- **Acceptable:** Remote, or onsite/hybrid in a relocation country (the developed markets plus Malaysia, Philippines, Thailand, Vietnam, Brunei and Timor-Leste)
- **Indonesia onsite:** Jabodetabek allowed (`onsite (prefers remote)`); other cities allowed as `relocation: domestic`, ranked lower
- **Too far / exclude:** Relocation required to a country outside the list above, or to a country with active conflict, severe political instability, or very limited tech market

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
