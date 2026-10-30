# Fastwork - data source reference

- Platform: https://fastwork.id/ (Indonesian (fastwork.id) and Thai (fastwork.co) service marketplace with a buyer job board).
- Access: Brave Search API `site:fastwork.id <keywords>` (and the same for fastwork.co).
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). No public API (checked 2026-10-30). Fastwork is mainly seller-listed services: the search returns the buyer job-board pages Brave has indexed. Thai-language posts fail the language gate.
- Fastwork pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is fastwork.id / fastwork.co or a subdomain.
