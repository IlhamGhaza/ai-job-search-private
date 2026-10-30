# jobstreet-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Brave web search

`GET {Brave endpoint}?q=site:{xx}.jobstreet.com/job {terms}`

web.results[]

## Environment variables

`BRAVE_SEARCH_API_TOKEN` (required), `BRAVE_SEARCH_API_URL` (tests).

## robots.txt / access check

id.jobstreet.com (and the other markets): `Disallow: */job/`, `*?`, `/graphql`, `/api/jobsearch/` -> never fetched.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
