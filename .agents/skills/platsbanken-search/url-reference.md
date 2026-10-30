# platsbanken-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Search

`GET https://jobsearch.api.jobtechdev.se/search?q=&limit=&offset=&published-after={minutes}&sort=pubdate-desc`

{total{value}, hits[]}: id, webpage_url, headline, employer, workplace_address, publication_date, application_deadline, employment_type, salary_type, salary_description, experience_required, workplace_model, application_details, description.

### Ad

`GET /ad/{id}`

same shape; `removed: true` when withdrawn.

## Environment variables

`JOBTECH_API_TOKEN` (optional), `JOBTECH_API_URL` (tests/mirrors).

## robots.txt / access check

jobsearch.api.jobtechdev.se has no robots.txt; the API is published open data.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
