# PeoplePerHour - data source reference

- Platform: https://peopleperhour.com/ (UK-based marketplace; clients post projects and freelancers send proposals (a limited number of free proposal credits per month)).
- Access: Brave Search API `site:peopleperhour.com/freelance-jobs <keywords>`.
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). PeoplePerHour's old public API is no longer offered to freelancers (checked 2026-10-30). Proposals spend proposal credits: record them as connects_or_bids_cost.
- PeoplePerHour pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is peopleperhour.com or a subdomain.
