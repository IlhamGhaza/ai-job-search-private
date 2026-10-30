# Workana - data source reference

- Platform: https://workana.com/ (Latin-America-focused marketplace (Spanish/Portuguese; some English projects)).
- Access: Brave Search API `site:workana.com/job <keywords>`.
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). No public API (checked 2026-10-30). Many projects are written in Spanish or Portuguese; the language gate in 04-job-evaluation.md still applies (Indonesian and English only in the profile).
- Workana pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is workana.com or a subdomain.
