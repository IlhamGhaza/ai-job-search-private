#!/usr/bin/env python3
"""Connector-based job and gig sources for /scrape: the deterministic half.

The claude.ai connectors (Indeed, ZipRecruiter, Dice, Upwork, Firecrawl) are MCP
tools: only the model can call them. This module holds everything around the
calls that must not depend on the model's judgment: which tools may be called,
what to ask them, how to turn their answers into the same job and gig records
every other source produces, the Firecrawl cache and call cap, and the run log.

Run from the repo root (see .claude/skills/job-scraper/SKILL.md, Step 1d):
    python tools/connector_sources.py status
    python tools/connector_sources.py plan [--connector C] [--jobs-only|--gigs-only] [--max-calls N]
    python tools/connector_sources.py check-tool --tool mcp__claude_ai_X__y [--args '{...}']
    python tools/connector_sources.py ingest --connector C --file response.json [--meta '{...}'] [--detail] [--pool P]
    python tools/connector_sources.py fc-begin [--cap N]
    python tools/connector_sources.py fc-check --query Q [--params '{...}'] | --url U   # before EVERY Firecrawl call
    python tools/connector_sources.py fc-store --query Q --file results.json [--params '{...}']
    python tools/connector_sources.py ws-run [--jobs-only|--gigs-only] [--source S]
    python tools/connector_sources.py report [--pool P]
    plan, check-tool, ingest and ws-run also take --intern off|remote|onsite (default remote).

Rules enforced here (and, for the deny list, in .claude/settings.json):
- A hardcoded allowlist per connector. Every Upwork tool that writes, spends
  Connects or changes the account is forbidden, as are LinkedIn Hiring Pro and
  Snagajob. `check-tool` answers for any tool name; unknown tools are refused.
- Firecrawl: search results and public pages only. No login, no saved browser
  profile, no stealth/enhanced/auto proxy, no Alexandria execution; LinkedIn
  feed and every Upwork page are never scraped; robots.txt is checked before a
  scrape. Each query is cached for 24 h and a run stops at its call cap.
- Internship searches follow --intern (off | remote | onsite, default remote):
  with off, no query asks for them and ingest drops them; otherwise job_rules.py
  decides. ZipRecruiter stays US/Canada with 5 results a call, paginated with
  offset and conversation_id.
- Records are the existing shapes: jobs as the portal contract (`type: job`),
  gigs as the freelance gig record (`type: gig`), a value the source does not
  state is null, never guessed.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from job_rules import DEFAULT_INTERN_MODE, INTERN_MODES, INTERN_TITLE, MOBILE, FLUTTER, SENIOR_TITLE, JUNIOR_TITLE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".claude" / "skills" / "job-scraper" / "connectors.md"
POOL = ROOT / "job_scraper" / "connector_pool.json"
FC_STATE = ROOT / "job_scraper" / "firecrawl_state.json"

# ---------------------------------------------------------------- tool policy

P = "mcp__claude_ai_"
ALLOWED_TOOLS = {
    "indeed": {f"{P}Indeed__search_jobs", f"{P}Indeed__get_job_details"},
    "ziprecruiter": {f"{P}ZipRecruiter__search_jobs"},
    "dice": {f"{P}Dice__search_jobs", f"{P}Dice__get_job_details"},
    # Read-only. find_jobs is read-only by its own help text; its actions are limited below.
    "upwork": {f"{P}Upwork__upwork__{t}" for t in ("list_accounts", "get_account", "find_jobs", "find_saved_jobs", "get_profile",
                                                  "list_freelancer_proposals", "get_tool_help")},
    "firecrawl": {f"{P}Firecrawl__firecrawl_search", f"{P}Firecrawl__firecrawl_scrape"},
    "gmail": {f"{P}Gmail__{t}" for t in ("search_threads", "get_thread", "get_message", "create_draft", "send_message")},
}
UPWORK_FIND_ACTIONS = {"search", "get", "smart_search"}
# Never called, even when loaded. The Upwork list is what settings.json denies.
FORBIDDEN_UPWORK = sorted(f"{P}Upwork__upwork__{t}" for t in (
    "manage_proposals", "send_message", "respond_to_offer", "boost_profile", "update_profile", "submit_milestones", "manage_meetings",
    "save_job", "set_tool_permission", "set_tool_mode", "start_attachment_upload", "confirm_attachment_upload", "store_uploaded_files",
    "confirm_preview", "get_preview", "submit_feedback"))
FORBIDDEN_SERVERS = [f"{P}LinkedIn_Hiring_Pro", f"{P}Snagajob"]
FORBIDDEN_TOOLS = FORBIDDEN_UPWORK + FORBIDDEN_SERVERS
ALL_ALLOWED = set().union(*ALLOWED_TOOLS.values())


def check_tool(name: str, args: dict | None = None, intern: str = DEFAULT_INTERN_MODE) -> dict:
    """{allowed, reason}. Deny first, then the per-connector allowlist; anything unknown is refused."""
    args = args or {}
    if any(name == s or name.startswith(s + "__") for s in FORBIDDEN_SERVERS):
        return {"allowed": False, "reason": "LinkedIn Hiring Pro (posts jobs) and Snagajob (US hourly retail) are never used"}
    if name in FORBIDDEN_UPWORK:
        return {"allowed": False, "reason": "Upwork tool that writes, spends Connects or changes the account"}
    if name not in ALL_ALLOWED:
        return {"allowed": False, "reason": "not on the connector allowlist"}
    if name.endswith("upwork__find_jobs") and args.get("action") not in UPWORK_FIND_ACTIONS:
        return {"allowed": False, "reason": f"find_jobs action must be one of {sorted(UPWORK_FIND_ACTIONS)}"}
    if name.endswith("Firecrawl__firecrawl_scrape"):
        bad = firecrawl_args_problem(args)
        if bad:
            return {"allowed": False, "reason": bad}
    if name.endswith("Firecrawl__firecrawl_search"):
        bad = firecrawl_args_problem(args)
        if bad:
            return {"allowed": False, "reason": bad}
    if name.endswith("ZipRecruiter__search_jobs"):
        bad = zip_args_problem(args, intern)
        if bad:
            return {"allowed": False, "reason": bad}
    if intern == "off" and name.endswith("Dice__search_jobs") and "INTERNSHIP" in [str(t).upper() for t in args.get("employment_types") or []]:
        return {"allowed": False, "reason": "INTERNSHIP is not searched with --intern off"}
    if intern == "off" and name.endswith("Indeed__search_jobs") and str(args.get("job_type") or "").lower() == "internship":
        return {"allowed": False, "reason": "internship is not searched with --intern off"}
    return {"allowed": True, "reason": "on the allowlist"}


def firecrawl_args_problem(args: dict) -> str | None:
    if str(args.get("proxy") or "basic").lower() != "basic":
        return "proxy must be basic: stealth, enhanced and auto bypass access controls"
    for key in ("profile", "alexandria", "actions", "lockdown"):
        if args.get(key):
            return f"'{key}' is not allowed: no login, saved sessions or catalogue execution"
    url = args.get("url")
    if url and (denied_url(url) or not re.match(r"^https?://", str(url))):
        return f"{url} is a page that is never scraped"
    return None


def zip_args_problem(args: dict, intern: str = DEFAULT_INTERN_MODE) -> str | None:
    if intern == "off" and "INTERNSHIP" in [str(t).upper() for t in args.get("employment_types") or []]:
        return "INTERNSHIP is not searched with --intern off"
    country = str(args.get("country_admin_code") or "US").upper()
    if country not in ("US", "CA"):
        return "ZipRecruiter covers the United States and Canada only"
    return None


# Pages Firecrawl never scrapes, and result URLs it never returns: Upwork forbids automated reads of its pages,
# the LinkedIn feed and logged-in areas are not public.
DENY_URL = [re.compile(p, re.I) for p in (
    r"^https?://([a-z0-9-]+\.)*upwork\.com(/|$)",
    r"^https?://([a-z0-9-]+\.)*linkedin\.com/(feed|login|checkpoint|uas|mynetwork|messaging|in/)",
    r"^https?://([a-z0-9-]+\.)*linkedin\.com/jobs/(collections|search)",
    r"/(login|signin|sign-in|auth|account|register)(/|\?|$)",
)]


def denied_url(url: str) -> bool:
    return any(rx.search(str(url)) for rx in DENY_URL)


# ---------------------------------------------------------------- config

DEFAULTS = {
    "indeed": {"enabled": "true", "type": "job", "countries": "SG,MY,PH,TH,VN,ID,JP,KR,AU,NZ,DE,NL,GB,IE,CA,US", "queries": "flutter developer|junior mobile developer", "max_detail": "0"},
    "ziprecruiter": {"enabled": "true", "type": "job", "countries": "US,CA", "max_pages": "0"},
    "dice": {"enabled": "true", "type": "job", "max_pages": "0", "max_detail": "0"},
    "upwork": {"enabled": "true", "type": "gig", "titles": "flutter|dart|flutterflow", "max_pages": "0", "max_get": "0"},
    "firecrawl": {"enabled": "true", "type": "both", "max_calls_per_run": "50", "cache_ttl_hours": "24", "web_search_provider": "firecrawl"},
    "gmail": {"enabled": "true", "type": "mail"},
}
LINE = re.compile(r"^\s*([a-z_]+)\.([a-z_]+)\s*=\s*(.*?)\s*$", re.M)


def load_config(path: Path = CONFIG) -> dict:
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return cfg
    for conn, key, value in LINE.findall(text):
        if conn in cfg:
            cfg[conn][key] = value.split("#", 1)[0].strip()
    return cfg


def enabled(cfg: dict, name: str) -> bool:
    return str(cfg.get(name, {}).get("enabled", "false")).lower() == "true"


def _cap(value, what: str) -> str:
    """How a plan note words a cap; 0 means none."""
    return f" (max {value} {what})" if str(value or "0") != "0" else ""


def _csv(value: str, sep: str = ",") -> list[str]:
    return [v.strip() for v in str(value).split(sep) if v.strip()]


# ---------------------------------------------------------------- helpers

def strip_html(text) -> str | None:
    if text is None:
        return None
    s = re.sub(r"<untrusted_participant_content>|</untrusted_participant_content>", "", str(text))
    s = re.sub(r"<\s*br\s*/?>|</\s*(p|li|div|h\d|ul|ol)\s*>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[ \t\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s or None


def num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(re.sub(r"[^\d.\-]", "", str(value)))
    except ValueError:
        return None


def iso_date(value) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def stated(value) -> str | None:
    s = str(value).strip() if value is not None else ""
    return None if s.lower() in ("", "n/a", "none", "null", "not specified") else s


EMPLOYMENT = [(r"intern", "internship"), (r"part[- ]?time", "part-time"), (r"contract|freelance", "contract"), (r"temporary", "temporary"),
              (r"full[- ]?time|permanent", "full-time")]


def employment(value) -> str | None:
    s = stated(value)
    if not s:
        return None
    return next((out for rx, out in EMPLOYMENT if re.search(rx, s, re.I)), None)


def make_job(**p) -> dict:
    base = {k: None for k in ("id", "title", "company", "location", "date", "url", "portal", "country", "employment_type", "seniority", "salary_min", "salary_max",
                              "salary_currency", "salary_period", "salary_gross_or_net", "salary_text", "remote_eligibility", "work_mode", "visa_sponsorship",
                              "relocation", "required_experience", "deadline", "apply_url", "description")}
    base.update(type="job", source_type="listing", verification_status="listing_from_connector", evidence=[])
    base.update(p)
    return base


# ---------------------------------------------------------------- Indeed

INDEED_FIELD = re.compile(r"\*\*([A-Za-z ]+):\*\*\s*(.*)")
COUNTRY_NAMES = {"SG": "Singapore", "MY": "Malaysia", "PH": "Philippines", "TH": "Thailand", "VN": "Vietnam", "ID": "Indonesia", "JP": "Japan",
                 "KR": "South Korea", "AU": "Australia", "NZ": "New Zealand", "DE": "Germany", "NL": "Netherlands", "GB": "United Kingdom",
                 "IE": "Ireland", "CA": "Canada", "US": "United States"}


def parse_indeed_blocks(text: str) -> list[dict]:
    blocks, cur = [], None
    for line in str(text).splitlines():
        m = INDEED_FIELD.match(line.strip())
        if not m:
            continue
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        if key == "job title":
            cur = {"title": val}
            blocks.append(cur)
        elif cur is not None:
            cur[key] = val
    return blocks


def indeed_record(block: dict, country: str | None) -> dict | None:
    if not block.get("job id") or not block.get("title"):
        return None
    loc = stated(block.get("location"))
    remote = bool(loc and loc.lower() == "remote")
    return make_job(
        id=block["job id"], title=block["title"], company=stated(block.get("company")), location=loc, date=iso_date(block.get("posted on")),
        url=stated(block.get("view job url")), apply_url=stated(block.get("view job url")), portal="indeed-connector",
        country=None if remote else country, work_mode="remote" if remote else None,
        employment_type=employment(block.get("job type")), salary_text=stated(block.get("compensation")),
        evidence=[f"Indeed connector search_jobs (country_code {country})" if country else "Indeed connector search_jobs"]
        + (["Remote listing found through a country search: eligibility for Indonesia not stated"] if remote else []),
    )


def indeed_detail(text: str) -> dict:
    """Description and fields from get_job_details markdown."""
    t = str(text)
    first = re.search(r"\*\*Compensation:\*\*[^\n]*\n", t)
    body = t[first.end():] if first else t
    return {"description": strip_html(body), "url": (re.search(r"\*\*View Job URL:\*\*\s*(\S+)", t) or [None, None])[1],
            "salary_text": stated((re.search(r"\*\*Compensation:\*\*\s*(.*)", t) or [None, ""])[1])}


# ---------------------------------------------------------------- ZipRecruiter

def zip_records(resp: dict, country: str | None, today: date | None = None, intern: str = DEFAULT_INTERN_MODE) -> list[dict]:
    today = today or date.today()
    out = []
    for r in resp.get("results") or []:
        jt = str(r.get("job_type") or "")
        if intern == "off" and re.search(r"intern", jt, re.I):
            continue
        sal = r.get("salary") or {}
        lo, hi = sal.get("min_annual"), sal.get("max_annual")
        usd = (country or "US").upper() == "US"
        remote = bool(re.search(r"·\s*Remote$", jt.strip()))
        optional = "remote optional" in jt.lower()
        days = r.get("days_ago")
        out.append(make_job(
            id=r.get("listing_key"), title=r.get("title"), company=r.get("company"), location=stated(r.get("location")),
            date=(today - timedelta(days=int(days))).isoformat() if isinstance(days, (int, float)) else None,
            url=r.get("job_redirect_url"), apply_url=r.get("job_redirect_url"), portal="ziprecruiter-connector", country=(country or "US").upper(),
            employment_type=employment(jt.split("·")[0]), work_mode="remote" if remote else None,
            salary_min=lo, salary_max=hi, salary_currency="USD" if usd and (lo or hi) else None, salary_period="year" if (lo or hi) else None,
            evidence=["ZipRecruiter connector search_jobs"] + (["remote optional (not fully remote)"] if optional else [])
            + ([] if usd or not (lo or hi) else ["salary currency not stated for Canada"]),
        ))
    return [j for j in out if j["id"] and j["title"]]


def next_zip_params(params: dict, resp: dict, page: int, max_pages: int = 0) -> dict | None:
    """The next page of one ZipRecruiter search, or None. Echoes conversation_id, offsets by what was returned. max_pages 0 is no cap."""
    meta = resp.get("meta") or {}
    count, total, limit = int(meta.get("count") or 0), meta.get("total"), int(meta.get("limit") or 5)
    offset = int(params.get("offset") or 0) + count
    if (max_pages and page + 1 >= max_pages) or count < limit or (total is not None and offset >= int(total)) or resp.get("status") not in (None, "OK"):
        return None
    nxt = {k: v for k, v in params.items() if k != "offset"}
    nxt["offset"] = offset
    if resp.get("conversation_id"):
        nxt["conversation_id"] = resp["conversation_id"]
    return nxt


# ---------------------------------------------------------------- Dice

def dice_salary(text) -> dict:
    s = stated(text)
    out = {"salary_text": s, "salary_min": None, "salary_max": None, "salary_currency": None, "salary_period": None}
    if not s:
        return out
    m = re.match(r"^\$?\s*([\d,]+(?:\.\d+)?)\s*(?:-|–|to)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*$", s)
    one = re.match(r"^\$?\s*([\d,]+(?:\.\d+)?)\s*$", s)
    nums = [num(g) for g in (m.groups() if m else one.groups() if one else ())]
    if nums and all(n and n >= 10_000 for n in nums):  # a bare yearly US figure; an hourly figure stays text
        out.update(salary_min=nums[0], salary_max=nums[1] if len(nums) > 1 else None, salary_currency="USD", salary_period="year")
    return out


def dice_records(resp: dict, intern: str = DEFAULT_INTERN_MODE) -> list[dict]:
    out = []
    for r in resp.get("data") or []:
        wt = [str(w) for w in r.get("workplaceTypes") or []]
        mode = {"remote": "remote", "on-site": "onsite", "hybrid": "hybrid"}.get(wt[0].lower()) if wt else None
        sponsor = r.get("willingToSponsor")
        out.append(make_job(
            id=r.get("guid"), title=r.get("title"), company=r.get("companyName"), location=stated(r.get("jobLocation")) or ("Remote" if mode == "remote" else None),
            date=iso_date(r.get("postedDate")), url=r.get("detailsPageUrl"), apply_url=r.get("detailsPageUrl"), portal="dice-connector", country="US",
            employment_type=employment(r.get("employmentType")), work_mode=mode, description=strip_html(r.get("summary")),
            visa_sponsorship="willing to sponsor (Dice employer filter)" if sponsor is True else None,
            evidence=["Dice connector search_jobs (United States)", f"willingToSponsor: {sponsor}"] + (["description is the search summary only"]),
            **dice_salary(r.get("salary")),
        ))
    return [j for j in out if j["id"] and j["title"] and not (intern == "off" and INTERN_TITLE.search(j["title"]))]


def dice_detail(resp: dict) -> dict:
    skills = [s.get("name") for s in resp.get("skills") or [] if isinstance(s, dict) and s.get("name")]
    return {"description": strip_html(resp.get("description")), "skills": skills}


# ---------------------------------------------------------------- Upwork

def upwork_budget(text, job_type) -> dict:
    s = str(text or "")
    nums = [num(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)]
    out = {"budget_type": None, "budget_min": None, "budget_max": None}
    if job_type in ("hourly", "fixed"):
        out["budget_type"] = job_type
    if nums:
        out["budget_min"] = nums[0]
        out["budget_max"] = nums[1] if len(nums) > 1 else (nums[0] if job_type == "fixed" else None)
    return out


def upwork_gig(row: dict) -> dict | None:
    """One find_jobs search or smart_search row -> a gig record. An already-applied gig is dropped by the caller."""
    if not row.get("id") or not row.get("title"):
        return None
    client = row.get("client") or {}
    ver = client.get("verification_status")
    level = str(row.get("experience_level") or "").upper()
    b = upwork_budget(row.get("budget"), row.get("job_type"))
    tier = row.get("proposals_tier")
    evidence = ["Upwork connector find_jobs (official, read-only)", "currency assumed USD (Upwork posts in USD; the search row has no symbol)"]
    if level:
        evidence.append(f"experience level: {level}")
    if row.get("engagement"):
        evidence.append(f"engagement: {row['engagement']}")
    if row.get("featured"):
        evidence.append("featured posting")
    if tier:
        evidence.append(f"proposals tier: {tier}")
    evidence.append("description truncated in search results; the get action returns the full text")
    return {
        "type": "gig", "platform": "Upwork", "gig_id": str(row["id"]), "url": row.get("url") or f"https://www.upwork.com/jobs/~02{row['id']}", "title": row["title"],
        "client_country": client.get("country"), "client_verified_payment": True if ver == "VERIFIED" else (False if ver else None),
        "client_rating": client.get("rating"), "client_hires": None, "client_total_spent": num(client.get("total_spent")),
        "budget_currency": "USD" if b["budget_min"] is not None else None, **b, "est_duration": row.get("duration"), "skills": list(row.get("skills") or []),
        "proposals_count": row.get("proposal_count"), "proposals_tier": tier, "connects_or_bids_cost": row.get("connect_price"),
        "posted_at": iso_date(row.get("published_date") or row.get("created_date")), "apply_method": "platform_proposal", "safety_screening": "unscreened",
        "evidence": evidence, "freelancer_locations": None, "source_type": "api", "verification_status": "listing_from_api",
        "description": strip_html(row.get("description_snippet")), "applied": bool(row.get("applied")),
    }


def upwork_detail(resp: dict) -> dict:
    """Merge fields from find_jobs `get`: client record, Connects cost, the full description, whether the posting already hired."""
    posting = ((resp.get("data") or {}).get("marketplaceJobPosting")) or {}
    rec = resp.get("client_record") or {}
    terms = posting.get("contractTerms") or {}
    out: dict = {"applied": bool(resp.get("applied"))}
    if "connects_cost" in resp:
        out["connects_or_bids_cost"] = resp.get("connects_cost")
    if rec:
        out["client_hires"] = rec.get("jobs_with_hires")
        out["client_total_spent"] = num(rec.get("spend_total"))
        out["client_rating"] = rec.get("feedback_score")
    desc = strip_html(((posting.get("content") or {}).get("description")))
    if desc:
        out["description"] = desc
    amount = (terms.get("fixedPriceContractTerms") or {}).get("amount") or {}
    if amount.get("currency"):
        out["budget_currency"] = amount["currency"]
    extra = []
    if rec:
        extra.append(f"client record: {rec.get('contracts_total')} contracts, {rec.get('hire_rate_percent')}% hire rate, {rec.get('jobs_posted')} jobs posted")
    hired = ((posting.get("activityStat") or {}).get("jobActivity") or {}).get("totalHired")
    if hired:
        extra.append(f"already hired {hired} freelancer(s) for this posting")
    if resp.get("can_apply") is False:
        extra.append("Upwork says this account cannot apply")
    out["_evidence"] = extra
    return out


# ---------------------------------------------------------------- Firecrawl leads

FIRECRAWL_SOURCES = {
    # type, kind, hosts (a hit is kept only on these), path prefix, queries
    "linkedin-posts": {"intern_query": "site:linkedin.com/posts flutter intern", "type": "job", "kind": "social_post", "hosts": ["linkedin.com"], "path": "/posts", "name": "LinkedIn posts",
                       "queries": ['site:linkedin.com/posts "junior flutter" hiring', "site:linkedin.com/posts flutter developer Indonesia hiring"]},
    "jobstreet": {"intern_query": "site:id.jobstreet.com flutter magang", "type": "job", "kind": "listing", "hosts": ["jobstreet.com"], "path": "", "name": "JobStreet",
                  "queries": [f"site:{h}.jobstreet.com flutter developer" for h in ("id", "my", "ph", "sg")]},
    "glints": {"intern_query": "site:glints.com/id flutter magang", "type": "job", "kind": "listing", "hosts": ["glints.com"], "path": "/", "name": "Glints", "queries": ["site:glints.com/id flutter developer"]},
    "kalibrr": {"intern_query": "site:kalibrr.com flutter intern", "type": "job", "kind": "listing", "hosts": ["kalibrr.com"], "path": "", "name": "Kalibrr", "queries": ["site:kalibrr.com flutter developer"]},
    "dealls": {"intern_query": "site:dealls.com flutter magang", "type": "job", "kind": "listing", "hosts": ["dealls.com"], "path": "", "name": "Dealls", "queries": ["site:dealls.com flutter developer"]},
    "global-remote": {"intern_query": "site:justremote.co flutter intern", "type": "job", "kind": "listing", "hosts": ["justremote.co", "remotely.jobs", "powertofly.com"], "path": "", "name": "Remote boards",
                      "queries": ["site:justremote.co flutter", "site:remotely.jobs flutter", "site:powertofly.com flutter developer"]},
    "contra": {"type": "gig", "hosts": ["contra.com"], "path": "/opportunity", "name": "Contra", "queries": ["site:contra.com/opportunity flutter"]},
    "peopleperhour": {"type": "gig", "hosts": ["peopleperhour.com"], "path": "/freelance-jobs", "name": "PeoplePerHour", "queries": ["site:peopleperhour.com/freelance-jobs flutter"]},
    "guru": {"type": "gig", "hosts": ["guru.com"], "path": "/work/detail", "name": "Guru", "queries": ["site:guru.com/work/detail flutter"]},
    "workana": {"type": "gig", "hosts": ["workana.com"], "path": "/job", "name": "Workana", "queries": ["site:workana.com/job flutter"]},
    "twine": {"type": "gig", "hosts": ["twine.net"], "path": "/projects", "name": "Twine", "queries": ["site:twine.net/projects flutter"]},
    "projects-co-id": {"type": "gig", "hosts": ["projects.co.id"], "path": "", "name": "Projects.co.id", "queries": ["site:projects.co.id flutter"]},
    "fastwork": {"type": "gig", "hosts": ["fastwork.id", "fastwork.co"], "path": "", "name": "Fastwork", "queries": ["site:fastwork.id flutter"]},
}


def web_queries(spec: dict, intern: str = DEFAULT_INTERN_MODE) -> list[str]:
    """A source's search-engine queries; job sources add one internship query unless --intern off."""
    extra = [spec["intern_query"]] if intern != "off" and spec.get("intern_query") else []
    return list(spec["queries"]) + extra


CREDITS_PER_SEARCH = 2  # observed: a 2-result web search reported creditsUsed 2; an estimate, not a price list


def on_hosts(url: str, hosts: list[str], path: str = "") -> bool:
    parts = urlsplit(str(url))
    host = (parts.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts) and parts.path.startswith(path or "/")


def clean_title(title: str | None, name: str) -> str:
    t = str(title or "").strip()
    t = re.sub(rf"\s+[|\-–]\s+{re.escape(name)}\b.*$", "", t, flags=re.I)
    return strip_html(t) or "(untitled)"


def firecrawl_leads(source: str, hits: list[dict], query: str = "", via: str = "firecrawl") -> list[dict]:
    """Search hits -> unverified leads in the shape of the other discovery skills. Denied URLs and off-host hits are dropped."""
    cfg = FIRECRAWL_SOURCES[source]
    label, prefix = ("Search router (Tavily, then Brave)", "websearch") if via == "router" else ("Firecrawl", "firecrawl")
    out = []
    for h in hits:
        url = h.get("url")
        if not url or denied_url(url) or not on_hosts(url, cfg["hosts"], cfg.get("path", "")):
            continue
        title, snippet = clean_title(h.get("title"), cfg["name"]), strip_html(h.get("description"))
        ev = [f'{label} search for "{query}" (page not fetched)']
        if cfg["type"] == "gig":
            out.append({"type": "gig", "platform": cfg["name"], "gig_id": url, "url": url, "title": title, "client_country": None, "client_verified_payment": None,
                        "client_rating": None, "client_hires": None, "client_total_spent": None, "budget_type": None, "budget_min": None, "budget_max": None,
                        "budget_currency": None, "est_duration": None, "skills": [], "proposals_count": None, "connects_or_bids_cost": None, "posted_at": None,
                        "apply_method": "platform_proposal", "safety_screening": "unscreened", "evidence": ev, "freelancer_locations": None,
                        "source_type": "search_lead", "verification_status": "unverified_lead", "description": snippet})
        else:
            out.append(make_job(id=url, title=title, url=url, portal=f"{prefix}-{source}", source_type=cfg["kind"], verification_status="unverified_lead",
                                description=snippet, evidence=ev + ([f"apply_method hint: portal_login"] if cfg["kind"] == "listing" else [])))
    return out


# ---------------------------------------------------------------- plan

def plan(cfg: dict, only: str | None = None, connector: str | None = None, max_calls: int | None = None, intern: str = DEFAULT_INTERN_MODE) -> dict:
    """The exact calls a run makes. The model runs them; check-tool and fc-check gate each one."""
    out: dict = {"connectors": {}}
    want = [connector] if connector else ["indeed", "ziprecruiter", "dice", "upwork", "firecrawl"]
    for name in want:
        c = cfg.get(name, {})
        kind = c.get("type", "job")
        entry = {"enabled": enabled(cfg, name), "type": kind, "calls": []}
        if not entry["enabled"] or (only and kind not in (only, "both")):
            entry["skipped"] = "disabled" if not entry["enabled"] else f"--{only}s-only"
            out["connectors"][name] = entry
            continue
        calls = entry["calls"]
        if name == "indeed":
            queries = _csv(c.get("queries", ""), "|")
            for cc in _csv(c.get("countries", "")):
                for q in queries:
                    calls.append({"tool": f"{P}Indeed__search_jobs", "args": {"search": q, "location": COUNTRY_NAMES.get(cc, cc), "country_code": cc}, "meta": {"country": cc}})
                calls.append({"tool": f"{P}Indeed__search_jobs", "args": {"search": queries[0], "location": "remote", "country_code": cc}, "meta": {"country": cc, "remote": True}})
                if intern != "off":
                    where = "remote" if intern == "remote" else COUNTRY_NAMES.get(cc, cc)
                    calls.append({"tool": f"{P}Indeed__search_jobs", "args": {"search": "flutter intern", "location": where, "country_code": cc},
                                  "meta": {"country": cc, "remote": intern == "remote", "intern": True}})
            entry["note"] = f"get_job_details only for ids `ingest` lists as detail_candidates{_cap(c.get('max_detail'), 'calls')}; empty countries are logged, not errors"
        elif name == "ziprecruiter":
            for cc in _csv(c.get("countries", "")):
                for remote in (True, False):
                    args = {"job_role": "flutter developer", "location": COUNTRY_NAMES.get(cc, cc), "country_admin_code": cc, "skills": ["Flutter", "Dart"],
                            "seniority_classes": ["NO_EXPERIENCE", "JUNIOR"]}
                    if remote:
                        args["location_types"] = ["REMOTE"]
                    calls.append({"tool": f"{P}ZipRecruiter__search_jobs", "args": args, "meta": {"country": cc, "remote": remote, "max_pages": int(c.get("max_pages", 0))}})
            entry["note"] = "5 results a call: pass `next` from ingest (offset + conversation_id) until it is null"
        elif name == "dice":
            base = {"keyword": "Flutter", "jobs_per_page": 20, "sort": "datePosted", "employment_types": ["FULLTIME", "CONTRACTS", "PARTTIME", "THIRD_PARTY"] + ([] if intern == "off" else ["INTERNSHIP"])}
            calls.append({"tool": f"{P}Dice__search_jobs", "args": {**base, "workplace_types": ["Remote"]}, "meta": {"query": "remote"}})
            calls.append({"tool": f"{P}Dice__search_jobs", "args": {**base, "willing_to_sponsor": True}, "meta": {"query": "sponsor"}})
            entry["note"] = f"US onsite without sponsorship lands in Needs verification (work eligibility); get_job_details for detail_candidates only{_cap(c.get('max_detail'), 'calls')}"
        elif name == "upwork":
            calls.append({"tool": f"{P}Upwork__upwork__list_accounts", "args": {}, "meta": {"yields": "org_uid"}})
            for t in _csv(c.get("titles", ""), "|"):
                calls.append({"tool": f"{P}Upwork__upwork__find_jobs", "args": {"action": "search", "org_uid": "<org_uid>",
                              "params": {"title": t, "verified_payment_only": True, "sort": "recency", "limit": 10}}, "meta": {"title": t, "max_pages": int(c.get("max_pages", 0))}})
            calls.append({"tool": f"{P}Upwork__upwork__find_jobs", "args": {"action": "smart_search", "org_uid": "<org_uid>",
                          "params": {"mode": "most_recent", "days_posted": 14, "verified_payment_only": True, "limit": 10}}, "meta": {"smart": True}})
            entry["note"] = (f"find_jobs get only for shortlisted gigs{_cap(c.get('max_get'), 'calls')}; stop on JOB_BROWSE_COOLDOWN; "
                             "paginate with cursor; read-only: never proposals, messages, offers or profile writes")
        elif name == "firecrawl":
            cap = int(c.get("max_calls_per_run", 50))
            provider = cfg.get("firecrawl", {}).get("web_search_provider", "firecrawl")
            if provider == "router":
                entry["skipped"] = "web_search_provider is router: run `ws-run` (Tavily, then Brave) instead of Firecrawl calls"
            elif provider != "firecrawl":
                entry["skipped"] = "web_search_provider is not firecrawl"
            for src, spec in FIRECRAWL_SOURCES.items():
                if only and spec["type"] != only:
                    continue
                for q in web_queries(spec, intern):
                    calls.append({"tool": f"{P}Firecrawl__firecrawl_search", "args": {"query": q, "sources": ["web"], "domainTools": False, "limit": 10},
                                  "meta": {"source": src, "query": q}})
            entry["cap"] = cap
            entry["queries"] = len(calls)
            entry["estimated_credits_max"] = min(len(calls), cap) * CREDITS_PER_SEARCH
            del calls[cap:]
        if max_calls is not None:
            del calls[max_calls:]
        entry["call_count"] = len(calls)
        out["connectors"][name] = entry
    return out


# ---------------------------------------------------------------- detail prefilter

def needs_detail(job: dict, intern: str = DEFAULT_INTERN_MODE) -> bool:
    """A first title/seniority pass so get_job_details is spent only where it can matter."""
    title = str(job.get("title") or "")
    if (intern == "off" and INTERN_TITLE.search(title)) or (SENIOR_TITLE.search(title) and not JUNIOR_TITLE.search(title)):
        return False
    return bool(FLUTTER.search(title) or MOBILE.search(title) or JUNIOR_TITLE.search(title))


# ---------------------------------------------------------------- pool, ingest, report

def load_pool(path: Path = POOL) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    for k in ("jobs", "gigs", "log"):
        data.setdefault(k, [])
    return data


def save_pool(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _merge(pool_list: list, rec: dict, keys: tuple) -> bool:
    ident = tuple(rec.get(k) for k in keys)
    for existing in pool_list:
        if tuple(existing.get(k) for k in keys) == ident:
            for k, v in rec.items():
                if existing.get(k) in (None, "", []) and v not in (None, "", []):
                    existing[k] = v
            return False
    pool_list.append(rec)
    return True


def read_response(path: Path):
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    # The Indeed tools answer {"result": "<markdown>"}.
    if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], str):
        return data["result"]
    return data


def ingest(connector: str, response, meta: dict | None = None, *, detail: bool = False, pool_path: Path = POOL, cfg: dict | None = None,
           today: date | None = None, window_days: int = 14, intern: str = DEFAULT_INTERN_MODE) -> dict:
    """Normalise one tool response into the pool. Never raises on an empty or odd answer: that is logged."""
    cfg = cfg or load_config()
    meta = meta or {}
    if connector not in ("indeed", "ziprecruiter", "dice", "upwork", "firecrawl"):
        raise ValueError(f"unknown connector {connector}")
    if not enabled(cfg, connector):
        raise ValueError(f"{connector} is disabled in connectors.md")
    pool = load_pool(pool_path)
    today = today or date.today()
    out: dict = {"connector": connector, "added": 0, "records": 0, "skipped_applied": 0, "skipped_old": 0, "detail_candidates": [], "next": None}
    jobs: list[dict] = []
    gigs: list[dict] = []
    if connector == "indeed":
        if detail:
            d = indeed_detail(response if isinstance(response, str) else json.dumps(response))
            for j in pool["jobs"]:
                if j["portal"] == "indeed-connector" and j["id"] == meta.get("job_id"):
                    j.update({k: v for k, v in d.items() if v})
            out["updated"] = meta.get("job_id")
        else:
            jobs = [r for r in (indeed_record(b, meta.get("country")) for b in parse_indeed_blocks(response if isinstance(response, str) else "")) if r]
            interns = [j for j in jobs if j["employment_type"] == "internship" or INTERN_TITLE.search(j["title"])] if intern == "off" else []
            jobs = [j for j in jobs if j not in interns]
            out["skipped_internship"] = len(interns)
    elif connector == "ziprecruiter":
        resp = response if isinstance(response, dict) else {}
        jobs = zip_records(resp, meta.get("country"), today, intern)
        out["next"] = next_zip_params(meta.get("params") or {}, resp, int(meta.get("page") or 0), int(meta.get("max_pages") or cfg["ziprecruiter"].get("max_pages", 0)))
    elif connector == "dice":
        resp = response if isinstance(response, dict) else {}
        if detail:
            d = dice_detail(resp)
            for j in pool["jobs"]:
                if j["portal"] == "dice-connector" and j["id"] == meta.get("job_id"):
                    j.update({k: v for k, v in d.items() if v and k != "skills"})
                    j["evidence"] = [e for e in j["evidence"] if e != "description is the search summary only"]
            out["updated"] = meta.get("job_id")
        else:
            jobs = dice_records(resp, intern)
            md = resp.get("metadata") or {}
            page_cap = int(cfg["dice"].get("max_pages", 0))
            if md.get("page") and md.get("totalPages") and md["page"] < md["totalPages"] and (not page_cap or md["page"] < page_cap):
                out["next"] = {"page_number": md["page"] + 1}
    elif connector == "upwork":
        resp = response if isinstance(response, dict) else {}
        if detail:
            d = upwork_detail(resp)
            extra = d.pop("_evidence", [])
            applied = d.pop("applied", False)
            for g in pool["gigs"]:
                if g["platform"] == "Upwork" and g["gig_id"] == str(meta.get("job_id")):
                    g.update({k: v for k, v in d.items() if v not in (None, "")})
                    g["evidence"] = [e for e in g["evidence"] if not e.startswith("description truncated")] + extra
                    g["applied"] = applied
            out["updated"] = meta.get("job_id")
        else:
            if resp.get("error_code") or resp.get("status") not in (None, "ok"):
                out["error"] = str(resp.get("error_code") or resp.get("status"))
            for row in resp.get("jobs") or resp.get("results") or []:
                g = upwork_gig(row)
                if g is None:
                    continue
                if g.pop("applied"):
                    out["skipped_applied"] += 1
                    continue
                gigs.append(g)
            page = resp.get("pageInfo") or {}
            if page.get("hasNextPage") or resp.get("hasMore"):
                out["next"] = {"cursor": page.get("endCursor") or resp.get("next_cursor")}
    elif connector == "firecrawl":
        hits = ((response or {}).get("data") or {}).get("web") if isinstance(response, dict) else None
        found = firecrawl_leads(meta["source"], hits or [], meta.get("query", ""), meta.get("via", "firecrawl"))
        (gigs if FIRECRAWL_SOURCES[meta["source"]]["type"] == "gig" else jobs).extend(found)
    out["returned"] = len(jobs) + len(gigs)
    cutoff = (today - timedelta(days=window_days)).isoformat()
    kept = []
    for j in jobs:
        if j.get("date") and j["date"] < cutoff:
            out["skipped_old"] += 1
        else:
            kept.append(j)
    for j in kept:
        out["added"] += _merge(pool["jobs"], j, ("portal", "id"))
        if connector in ("indeed", "dice") and needs_detail(j, intern):
            out["detail_candidates"].append(j["id"])
    kept_gigs = []
    for g in gigs:
        if g.get("posted_at") and g["posted_at"] < cutoff:
            out["skipped_old"] += 1
        else:
            kept_gigs.append(g)
    for g in kept_gigs:
        out["added"] += _merge(pool["gigs"], g, ("platform", "gig_id"))
    out["records"] = len(kept) + len(kept_gigs)
    # Dice and Upwork are searched newest first, so a page with nothing in the window ends the search.
    if connector in ("dice", "upwork") and out["returned"] and not out["records"]:
        out["next"] = None
    out["empty"] = out["returned"] == 0 and not detail and "updated" not in out
    out["all_filtered"] = out["returned"] > 0 and out["records"] == 0
    pool["log"].append({"connector": connector, "meta": {k: v for k, v in meta.items() if k in ("country", "remote", "query", "source", "title", "page")},
                        "records": out["records"], "returned": out["returned"], "empty": out["empty"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    save_pool(pool_path, pool)
    return out


def report(pool_path: Path = POOL) -> dict:
    pool = load_pool(pool_path)
    per: dict = {}
    for entry in pool["log"]:
        row = per.setdefault(entry["connector"], {"calls": 0, "records": 0, "empty": []})
        row["calls"] += 1
        row["records"] += entry["records"]
        row["returned"] = row.get("returned", 0) + entry.get("returned", entry["records"])
        if entry["empty"]:
            row["empty"].append(entry["meta"].get("country") or entry["meta"].get("query") or entry["meta"].get("source") or entry["meta"].get("title") or "?")
    return {"per_connector": per, "jobs_in_pool": len(pool["jobs"]), "gigs_in_pool": len(pool["gigs"])}


# ---------------------------------------------------------------- Firecrawl budget and cache

def fc_load(path: Path = FC_STATE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("run", {"calls": 0, "cap": 50, "cache_hits": 0, "refused": 0})
    data.setdefault("cache", {})
    return data


def fc_save(data: dict, path: Path = FC_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def fc_key(query: str | None, params: dict | None, url: str | None) -> str:
    material = json.dumps([str(query or "").strip().lower(), params or {}, url or ""], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def fc_begin(cap: int | None = None, *, path: Path = FC_STATE, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    data = fc_load(path)
    cap = cap if cap is not None else int(cfg["firecrawl"].get("max_calls_per_run", 50))
    data["run"] = {"calls": 0, "cap": cap, "cache_hits": 0, "refused": 0}
    fc_save(data, path)
    return data["run"]


def fc_check(query: str | None = None, params: dict | None = None, url: str | None = None, *, path: Path = FC_STATE, cfg: dict | None = None,
             now: datetime | None = None, robots=None) -> dict:
    """Ask before every Firecrawl call. use_cache | call (one more used) | cap_reached | refused. A cache hit costs nothing."""
    cfg = cfg or load_config()
    now = now or datetime.now(timezone.utc)
    if not enabled(cfg, "firecrawl"):
        return {"action": "refused", "reason": "firecrawl is disabled in connectors.md"}
    data = fc_load(path)
    run = data["run"]
    if url is not None:
        bad = firecrawl_args_problem({"url": url})
        if bad:
            run["refused"] += 1
            fc_save(data, path)
            return {"action": "refused", "reason": bad}
        gate = robots or _robots_gate
        code, msg = gate(url)
        if code != 0:
            run["refused"] += 1
            fc_save(data, path)
            return {"action": "refused", "reason": f"robots.txt: {msg}"}
    key = fc_key(query, params, url)
    ttl = timedelta(hours=float(cfg["firecrawl"].get("cache_ttl_hours", 24)))
    hit = data["cache"].get(key)
    if hit and now - datetime.fromisoformat(hit["ts"]) < ttl:
        run["cache_hits"] += 1
        fc_save(data, path)
        return {"action": "use_cache", "results": hit["results"], "age_hours": round((now - datetime.fromisoformat(hit["ts"])).total_seconds() / 3600, 1)}
    if run["calls"] >= run["cap"]:
        fc_save(data, path)
        return {"action": "cap_reached", "cap": run["cap"], "calls": run["calls"]}
    run["calls"] += 1
    fc_save(data, path)
    return {"action": "call", "key": key, "used": run["calls"], "remaining": run["cap"] - run["calls"]}


def fc_store(results, query: str | None = None, params: dict | None = None, url: str | None = None, *, path: Path = FC_STATE,
             now: datetime | None = None) -> dict:
    data = fc_load(path)
    key = fc_key(query, params, url)
    data["cache"][key] = {"ts": (now or datetime.now(timezone.utc)).isoformat(), "results": results}
    fc_save(data, path)
    return {"stored": key, "entries": len(data["cache"])}


def ws_run(cfg: dict | None = None, only: str | None = None, source: str | None = None, *, pool_path: Path = POOL, route=None,
           intern: str = DEFAULT_INTERN_MODE) -> dict:
    """Run every web-search query through the router (Tavily, then Brave) and ingest the hits as unverified leads.

    One router call per query; the router enforces the monthly caps. Stops early when every provider is exhausted.
    """
    cfg = cfg or load_config()
    if route is None:
        import search_router

        route = search_router.route
    out: dict = {"queries": 0, "records": 0, "added": 0, "by_provider": {}, "exhausted": False, "errors": []}
    for src, spec in FIRECRAWL_SOURCES.items():
        if (source and src != source) or (only and spec["type"] != only):
            continue
        for q in web_queries(spec, intern):
            res = route(q, 10)
            if not res.get("provider"):
                out["exhausted"] = True
                out["errors"] = res.get("errors", [])
                return out
            hits = [{"url": r.get("url"), "title": r.get("title"), "description": r.get("snippet")} for r in res.get("results", [])]
            got = ingest("firecrawl", {"data": {"web": hits}}, {"source": src, "query": q, "via": "router"}, pool_path=pool_path, cfg=cfg, intern=intern)
            out["queries"] += 1
            out["records"] += got["records"]
            out["added"] += got["added"]
            out["by_provider"][res["provider"]] = out["by_provider"].get(res["provider"], 0) + 1
    return out


def _robots_gate(url: str):
    import robots_check

    return robots_check.gate(url)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Connector sources for /scrape")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    pl = sub.add_parser("plan")
    pl.add_argument("--connector")
    pl.add_argument("--jobs-only", action="store_true")
    pl.add_argument("--gigs-only", action="store_true")
    pl.add_argument("--max-calls", type=int)
    ct = sub.add_parser("check-tool")
    ct.add_argument("--tool", required=True)
    ct.add_argument("--args", default="{}")
    ig = sub.add_parser("ingest")
    ig.add_argument("--connector", required=True)
    ig.add_argument("--file", type=Path, required=True)
    ig.add_argument("--meta", default="{}")
    ig.add_argument("--detail", action="store_true")
    ig.add_argument("--pool", type=Path, default=POOL)
    fb = sub.add_parser("fc-begin")
    fb.add_argument("--cap", type=int)
    fk = sub.add_parser("fc-check")
    fk.add_argument("--query")
    fk.add_argument("--url")
    fk.add_argument("--params", default="{}")
    fs = sub.add_parser("fc-store")
    fs.add_argument("--query")
    fs.add_argument("--url")
    fs.add_argument("--params", default="{}")
    fs.add_argument("--file", type=Path, required=True)
    wr = sub.add_parser("ws-run")
    wr.add_argument("--jobs-only", action="store_true")
    wr.add_argument("--gigs-only", action="store_true")
    wr.add_argument("--source")
    rp = sub.add_parser("report")
    for parser in (pl, ct, ig, wr):
        parser.add_argument("--intern", nargs="?", const=DEFAULT_INTERN_MODE, default=DEFAULT_INTERN_MODE, choices=INTERN_MODES)
    rp.add_argument("--pool", type=Path, default=POOL)
    args = p.parse_args(argv)

    def emit(obj) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    try:
        cfg = load_config()
        if args.cmd == "status":
            emit({"config": {k: {"enabled": enabled(cfg, k), "type": cfg[k].get("type")} for k in cfg}, "forbidden": FORBIDDEN_TOOLS,
                  "allowed": {k: sorted(v) for k, v in ALLOWED_TOOLS.items()}})
        elif args.cmd == "plan":
            if args.jobs_only and args.gigs_only:
                raise ValueError("--jobs-only and --gigs-only cannot be combined")
            emit(plan(cfg, "job" if args.jobs_only else "gig" if args.gigs_only else None, args.connector, args.max_calls, args.intern))
        elif args.cmd == "check-tool":
            out = check_tool(args.tool, json.loads(args.args), args.intern)
            emit(out)
            return 0 if out["allowed"] else 3
        elif args.cmd == "ingest":
            emit(ingest(args.connector, read_response(args.file), json.loads(args.meta), detail=args.detail, pool_path=args.pool, cfg=cfg, intern=args.intern))
        elif args.cmd == "fc-begin":
            emit(fc_begin(args.cap, cfg=cfg))
        elif args.cmd == "fc-check":
            out = fc_check(args.query, json.loads(args.params), args.url, cfg=cfg)
            emit(out)
            return 0 if out["action"] in ("call", "use_cache") else 3
        elif args.cmd == "fc-store":
            emit(fc_store(json.loads(args.file.read_text(encoding="utf-8")), args.query, json.loads(args.params), args.url))
        elif args.cmd == "ws-run":
            if args.jobs_only and args.gigs_only:
                raise ValueError("--jobs-only and --gigs-only cannot be combined")
            if args.source and args.source not in FIRECRAWL_SOURCES:
                raise ValueError(f"unknown source {args.source}; one of {sorted(FIRECRAWL_SOURCES)}")
            out = ws_run(cfg, "job" if args.jobs_only else "gig" if args.gigs_only else None, args.source, intern=args.intern)
            emit(out)
            return 3 if out["exhausted"] else 0
        elif args.cmd == "report":
            emit(report(args.pool))
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc), "code": "BAD_INPUT"}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
