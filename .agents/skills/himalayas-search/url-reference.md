# himalayas-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Search

`GET https://himalayas.app/jobs/api/search?q={q}[&country={c}][&worldwide=true]`

{totalCount, jobs[]}: title, excerpt, companyName, employmentType, minSalary, maxSalary, currency, salaryPeriod, seniority[], locationRestrictions[], timezoneRestrictions[], description, pubDate (epoch s), expiryDate, applicationLink, guid.

### Detail

`GET {guid} (HTML)`

schema.org JobPosting JSON-LD.

## Environment variables

`HIMALAYAS_API_URL` (tests/mirrors).

## robots.txt / access check

Disallows `/apply`, `/jobs?page=`, `/jobs*&page=`, `/jobs/*?page=` (and companies/talent paging). Search page 1 and job pages are allowed.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
