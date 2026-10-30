# arbeitnow-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Jobs

`GET https://www.arbeitnow.com/api/job-board-api?page={n}[&visa_sponsorship=true][&remote=true]`

{data[], links{next}, meta}: slug, company_name, title, description (escaped HTML), remote, url, tags, job_types, location, created_at (epoch s).

## Environment variables

`ARBEITNOW_API_URL` (tests/mirrors).

## robots.txt / access check

`Disallow:` (empty) for `*`; only `/*?__hstc` disallowed.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
