# Contra - data source reference

- Platform: https://contra.com/ (commission-free freelance network; opportunities are posted by clients and freelancers apply with a profile).
- Access: Brave Search API `site:contra.com/opportunity <keywords>`.
  Endpoint `https://api.search.brave.com/res/v1/web/search`, header
  `X-Subscription-Token`, override with `BRAVE_SEARCH_API_URL` (tests).
- Official API: none for gig search (checked 2026-10-30). No public API for opportunities (checked 2026-10-30). Contra is open worldwide; payouts go through Contra (Stripe/PayPal) - confirm Indonesia payouts in your account settings.
- Contra pages: never fetched by this skill (no robots.txt read needed);
  `detail` returns `MANUAL_ONLY`.
- Lead filter: a hit is kept only when its host is contra.com or a subdomain.
