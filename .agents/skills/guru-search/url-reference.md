# Guru - data source reference

- Platform: https://guru.com/ (global marketplace; clients post jobs and freelancers spend Bids to quote).
- Access: Brave Search API `site:guru.com/work/detail <keywords>`.
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). Guru has no public job-search API (checked 2026-10-30). Quotes spend Bids: record them as connects_or_bids_cost.
- Guru pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is guru.com or a subdomain.
