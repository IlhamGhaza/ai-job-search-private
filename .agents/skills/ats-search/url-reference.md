# ats-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Greenhouse

`GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`

`jobs[]`: id, title, absolute_url, location.name, first_published, content (HTML, entity-escaped), application_deadline. Detail: `/v1/boards/{board}/jobs/{id}?pay_transparency=true` adds `pay_input_ranges[]` (min_cents, max_cents, currency_type).

### Lever

`GET https://api.lever.co/v0/postings/{board}?mode=json`

array: id, text, hostedUrl, applyUrl, categories{location, commitment}, createdAt (ms), descriptionPlain, lists[], workplaceType, salaryRange{min,max,currency,interval}, country. Detail: `/v0/postings/{board}/{id}`.

### Ashby

`GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true`

`jobs[]`: id, title, location, isRemote, workplaceType, employmentType, publishedAt, jobUrl, applyUrl, descriptionHtml, isListed, compensation.summaryComponents[].

### Workable

`GET https://apply.workable.com/api/v1/widget/accounts/{board}?details=true`

{name, jobs[]}: title, shortcode, url, application_url, employment_type, telecommuting, experience, locations[], published_on, description.

### Recruitee

`GET https://{board}.recruitee.com/api/offers/`

`offers[]`: slug, title, company_name, location, country_code, remote/hybrid/on_site, careers_url, careers_apply_url, published_at, employment_type_code, experience_code, salary{min,max,currency,period}, description, requirements. Detail: `/api/offers/{slug}`.

## Environment variables

`ATS_API_BASE_OVERRIDE` (tests only: routes every provider to `<url>/<ats>`), `GREENHOUSE_API_URL`, `LEVER_API_URL`, `ASHBY_API_URL` (mirrors).

## robots.txt / access check

boards-api.greenhouse.io: only `/embed/` disallowed. api.lever.co: `Allow: /`. api.ashbyhq.com: no robots.txt. apply.workable.com: nothing disallowed. api.smartrecruiters.com: `Disallow: /` for `*` -> not implemented.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
