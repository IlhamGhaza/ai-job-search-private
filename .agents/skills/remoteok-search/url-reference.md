# remoteok-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Jobs

`GET https://remoteok.com/api[?tag={tag}]`

array; [0] = {legal}, then: id, slug, epoch, date, company, position, tags, description, location, salary_min, salary_max, apply_url, url.

## Environment variables

`REMOTEOK_API_URL` (tests/mirrors).

## robots.txt / access check

`User-agent: *` `Allow: /`; Content-Signal `search=yes,ai-train=no,use=reference`.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
