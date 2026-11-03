# Connector sources for /scrape

`/scrape` (Step 1d) and `/gigs` also read the claude.ai connectors below. They are MCP tools, not CLI skills: the model calls them, and `tools/connector_sources.py` plans the calls, gates each one, and turns the answers into the same job and gig records every other source produces. A connector that is not loaded in the session is reported as `missing` and skipped; it never fails the run.

Switch a connector off with `enabled = false`. For `max_pages`, `max_detail` and `max_get`, `0` means no cap: a search runs until the source has no next page, or for Dice and Upwork until a whole page is older than 14 days. The settings below are read by `tools/connector_sources.py` (lines of the form `connector.key = value`, in any fenced block or plain text).

```
# Indeed - jobs. One call per country and query, plus a `remote` call per country. Empty countries are logged, not errors.
indeed.enabled = true
indeed.type = job
indeed.countries = SG,MY,PH,TH,VN,ID,JP,KR,AU,NZ,DE,NL,GB,IE,CA,US
indeed.queries = flutter developer|junior mobile developer
indeed.max_detail = 0

# ZipRecruiter - jobs, US and Canada only, 5 results a call.
ziprecruiter.enabled = true
ziprecruiter.type = job
ziprecruiter.countries = US,CA
ziprecruiter.max_pages = 0

# Dice - US tech jobs. Remote, and separately willing_to_sponsor.
dice.enabled = true
dice.type = job
dice.max_pages = 0
dice.max_detail = 0

# Upwork - gigs, through the official connector (read-only). Replaces the search-engine mode of upwork-search.
upwork.enabled = true
upwork.type = gig
upwork.titles = flutter|dart|flutterflow
upwork.max_pages = 0
upwork.max_get = 0

# Firecrawl - the web-search provider for portals without an API (instead of the Brave Search API).
firecrawl.enabled = true
firecrawl.type = both
firecrawl.web_search_provider = router    # router = Tavily, then Brave as last resort (tools/search_router.py); firecrawl = MCP calls
firecrawl.max_calls_per_run = 50
firecrawl.cache_ttl_hours = 24

# Gmail - /gmail-sync reads it; /submit and /autopilot send through it (one "Send all?" approval, always).
gmail.enabled = true
```

## Allowed and forbidden tools

Hardcoded in `tools/connector_sources.py` (`ALLOWED_TOOLS`, `FORBIDDEN_TOOLS`) and denied in `.claude/settings.json`. Ask `python3 tools/connector_sources.py check-tool --tool <name>` when unsure; an unknown tool is refused.

| Connector | Allowed (read-only) | Never |
|---|---|---|
| Indeed | `search_jobs`, `get_job_details` | `get_resume`, everything else |
| ZipRecruiter | `search_jobs` | everything else |
| Dice | `search_jobs`, `get_job_details` | everything else |
| Upwork | `list_accounts`, `get_account`, `find_jobs` (actions `search`, `get`, `smart_search`), `find_saved_jobs`, `get_profile`, `list_freelancer_proposals`, `get_tool_help` | `manage_proposals`, `send_message`, `respond_to_offer`, `boost_profile`, `update_profile`, `submit_milestones`, `manage_meetings`, `save_job`, `set_tool_permission`, `set_tool_mode`, `start_attachment_upload`, `confirm_attachment_upload`, `store_uploaded_files`, `confirm_preview`, `get_preview`, `submit_feedback`, anything else that writes, spends Connects or changes the account |
| Firecrawl | `firecrawl_search`, `firecrawl_scrape` (basic proxy, public pages, no profile) | stealth/enhanced/auto proxy, saved browser profiles, Alexandria execution, scraping LinkedIn feed or any Upwork page |
| Gmail | `search_threads`, `get_thread`, `get_message`, `create_draft`, `send_message` (sending only through `tools/email_send.py`) | everything else |
| LinkedIn Hiring Pro | - | all (it posts jobs for employers; never call `preview_job_posting`) |
| Snagajob | - | all (US hourly retail) |

LinkedIn job search stays on `linkedin-search`; Firecrawl only finds public LinkedIn posts.

## Record notes

- **Age:** `ingest` drops any job or gig dated more than 14 days ago and counts it in `skipped_old`. A record with no date stays in the pool, and `/autopilot` does not select it.
- **Indeed:** results are markdown; the id is `JOBSEARCH_n`, the link a `to.indeed.com` redirect, salary is usually `N/A` (so `needs_salary_verification`). A `Remote` listing found through a country search carries no country: eligibility for Indonesia is unknown.
- **ZipRecruiter:** salary is annual USD for US; for Canada the currency is not stated, so it stays null. `Remote optional` is not remote. `INTERNSHIP` follows `--intern`: with `off` it is neither searched nor kept.
- **Dice:** the `guid` (not `id`) goes to `get_job_details`. A salary like `75000 - 199000` becomes USD per year; `Depends on Experience` stays text.
- **Upwork:** search rows carry no hire count, no Connects cost and a truncated description; `get` adds `client_record` (hires), `connects_cost` and the full text. Gigs with `applied: true` are dropped, `expert` level is not a junior fit, a posting that already hired is rejected.
- **Firecrawl:** `fc-check` before every call (cache, then cap), `fc-store` after. One search is about 2 credits; the default cap is 50 calls a run.
