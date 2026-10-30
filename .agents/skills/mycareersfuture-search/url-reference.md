# mycareersfuture-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Search

`GET https://api.mycareersfuture.gov.sg/v2/jobs?search={q}&limit={n}&page={0-based}&sortBy=new_posting_date`

{results[], total}: uuid, title, description, minimumYearsExperience, employmentTypes[], positionLevels[], postedCompany, address, salary{minimum, maximum, type.salaryType}, metadata{newPostingDate, expiryDate, jobDetailsUrl, isHideSalary}.

### Job

`GET /v2/jobs/{uuid}`

same object.

## Environment variables

`MCF_API_URL` (tests/mirrors).

## robots.txt / access check

www.mycareersfuture.gov.sg: `User-agent: *` `Disallow:` (empty). api.mycareersfuture.gov.sg: no robots.txt.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
