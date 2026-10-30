# Twine - data source reference

- Platform: https://twine.net/ (creative and tech freelance marketplace (UK-based)).
- Access: Brave Search API `site:twine.net/projects <keywords>`.
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). No public API (checked 2026-10-30). Mostly creative work; mobile-app projects appear occasionally.
- Twine pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is twine.net or a subdomain.
