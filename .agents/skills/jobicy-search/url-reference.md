# jobicy-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Jobs

`GET https://jobicy.com/api/v2/remote-jobs?count={n}&tag={t}&geo={g}&industry={i}`

{jobs[]}: id, url, jobTitle, companyName, jobIndustry[], jobType[], jobGeo, jobLevel, jobExcerpt, jobDescription, pubDate, salaryMin, salaryMax, salaryCurrency, salaryPeriod.

## Environment variables

`JOBICY_API_URL` (tests/mirrors).

## robots.txt / access check

Disallows query paths like `/*?s=`, `/*?q=`; the API path and `/jobs/` pages are allowed.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
