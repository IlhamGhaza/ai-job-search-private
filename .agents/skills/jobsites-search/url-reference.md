# jobsites-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Brave web search

`GET {Brave endpoint}?q=site:{host}{path} {terms}`

web.results[]

### Posting page

`GET {posting URL} after GET {origin}/robots.txt`

schema.org JobPosting JSON-LD.

## Environment variables

`BRAVE_SEARCH_API_TOKEN` (required for search), `BRAVE_SEARCH_API_URL` (tests).

## robots.txt / access check

Checked 2026-10-30 for every board; see the `note` and `fetchable` fields in `cli/src/sites.ts`. Re-checked live on every `detail`.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
