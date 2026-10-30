# nav-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Token

`GET https://pam-stilling-feed.nav.no/api/publicToken`

text with a JWT.

### Feed

`GET /api/v1/feed (Authorization: Bearer, If-Modified-Since)`

JSON Feed: items[]{id, url, title, date_modified, _feed_entry{uuid, status, title, businessName}}, next_url.

### Entry

`GET /api/v1/feedentry/{uuid}`

{uuid, status, ad_content{title, description, employer, workLocations, published, expires, applicationDue, applicationUrl, link, engagementtype, extent}}.

## Environment variables

`NAV_API_TOKEN` (optional), `NAV_FEED_URL` (tests/mirrors).

## robots.txt / access check

arbeidsplassen.nav.no: `Disallow:` (empty). The feed API requires a bearer token, which NAV publishes publicly.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
