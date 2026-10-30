# Upwork - data source reference

- API: GraphQL `POST https://api.upwork.com/graphql`, header
  `Authorization: Bearer <UPWORK_ACCESS_TOKEN>`; override `UPWORK_GRAPHQL_URL` (tests).
  Query `marketplaceJobPostingsSearch(marketPlaceJobFilter: {searchExpression_eq,
  pagination_eq {after, first}}, searchType: USER_JOBS_SEARCH, sortAttributes: [{field: RECENCY}])`;
  detail `marketplaceJobPosting(id:)`. Docs: https://www.upwork.com/developer/documentation/graphql
  (behind a login wall when checked 2026-10-30; confirm field names by introspection).
- Key application: https://www.upwork.com/developer/keys/apply (ID-verified account,
  manual approval). The public API has no proposal-submission mutation.
- Fallback: Brave Search API `site:upwork.com/freelance-jobs/apply <keywords>`.
- Never fetched: any upwork.com page (the Terms of Use forbid scraping; robots.txt is not
  consulted because no page is requested).
- Job URL: `https://www.upwork.com/jobs/<ciphertext>`.
