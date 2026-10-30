# Freelancer.com - data source reference

- API base `https://www.freelancer.com/api` (override `FREELANCER_API_URL` for tests),
  header `freelancer-oauth-v1: <FREELANCER_OAUTH_TOKEN>`. Docs: https://developers.freelancer.com
  (field names cross-checked against third-party samples on 2026-10-30 because the official
  page path had moved; re-check if a field comes back empty).
- Search: `GET /projects/0.1/projects/active/?query=&limit=&offset=&full_description=true&job_details=true
  &user_details=true&user_country_details=true&user_status=true&user_employer_reputation=true
  &project_types[]=fixed&project_types[]=hourly&sort_field=time_updated`
  -> `{status, result: {projects[], users{id: user}, total_count}}`.
- Detail: `GET /projects/0.1/projects/<id>/` or `/projects/0.1/projects/?seo_urls[]=<path>`,
  then `GET /users/0.1/users/<owner_id>/?country_details=true&status=true&employer_reputation=true`.
- Project URL: `https://www.freelancer.com/projects/<seo_url>`.
- Never fetched: freelancer.com web pages. Bids are never placed through the API.
