# Projects.co.id - data source reference

- Platform: https://projects.co.id/ (Indonesian project marketplace (IDR budgets, Indonesian-language projects)).
- Access: Brave Search API `site:projects.co.id/public/browse_projects/view <keywords>`.
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). No public API (checked 2026-10-30). Budgets are in IDR; the rate floor applies unchanged.
- Projects.co.id pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is projects.co.id or a subdomain.
