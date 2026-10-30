# weworkremotely-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Feeds

`GET https://weworkremotely.com/categories/{category}.rss | /remote-jobs.rss`

RSS 2.0 items: title, region, category, type, description (escaped HTML), pubDate, guid, link.

## Environment variables

`WWR_BASE_URL` (tests/mirrors).

## robots.txt / access check

`Allow: /`; disallows `/admin/`, `/account/`, `/job-seekers/account/`, `/manage-company/`.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
