# remotive-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Jobs

`GET https://remotive.com/api/remote-jobs?category=software-dev&search={q}`

{jobs[]}: id, url, title, company_name, category, tags, job_type, publication_date, candidate_required_location, salary (free text), description (HTML).

## Environment variables

`REMOTIVE_API_URL` (tests/mirrors).

## robots.txt / access check

remotive.com/robots.txt returned 200 with no rule for the API path. API notice terms quoted above.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
