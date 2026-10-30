# linkedin-posts-search - URL reference

Recorded 2026-10-30 from live reconnaissance (low volume). Update this file
when the source changes its API.

## Endpoints

### Brave web search

`GET https://api.search.brave.com/res/v1/web/search?q=&count=&offset=&freshness= (X-Subscription-Token)`

web.results[]: title, url, description, age, page_age.

## Environment variables

`BRAVE_SEARCH_API_TOKEN` (required), `BRAVE_SEARCH_API_URL` (tests).

## robots.txt / access check

LinkedIn is not contacted. Brave Search API is a keyed commercial API used under its terms.

## Mapping rules

- Contract fields: `id`, `title`, `company`, `location`, `date` (YYYY-MM-DD), `url`.
- Optional fields are filled **only** from values the source states; everything else is `null`.
- Salary numbers are copied only when the source gives numbers; free-text salary stays in `salary_text`.
