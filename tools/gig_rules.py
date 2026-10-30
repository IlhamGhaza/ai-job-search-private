#!/usr/bin/env python3
"""Deterministic rules for freelance gigs (/gigs), on top of the job rules.

Code, not model judgment, so a persuasive gig cannot talk its way past them.
Reuses tools/job_rules.py (Cambodia/India rules, seniority, Flutter relevance,
unpaid and safety patterns), tools/fx_rates.py (daily FX cache) and
tools/posting_guard.py (prompt-injection scan); gig-specific rules live here.

Run from the repo root:
    python tools/gig_rules.py evaluate --in <gigs.json> [--offline] [--today YYYY-MM-DD]
        [--monthly-floor 5000000] [--hours-per-month 173] [--tracker freelance_tracker.csv]

<gigs.json> is a JSON array, {"results": [...]} (one CLI's output) or
{"runs": [{"results": [...]}, ...]} (several CLIs). Output:
{"sections": {"good_fits", "needs_budget_client_review", "manual_safety_review",
"rejected"}, "vetted_networks", "platforms", "duplicates_dropped", "counts", "fx", "config"}.

The gig record (every field present, null when the source does not state it,
never guessed): platform, gig_id, url, title, client_country,
client_verified_payment, client_rating, client_hires, client_total_spent,
budget_type (hourly|fixed), budget_min, budget_max, budget_currency,
est_duration, skills, proposals_count, connects_or_bids_cost, posted_at,
apply_method, safety_screening, evidence, plus freelancer_locations,
source_type (api|search_lead), verification_status, description.

Rules:
1. Rate floor. Hourly: the minimum rate converted to IDR must be >= monthly
   floor / hours per month (IDR 5,000,000 / 173 h = IDR 28,902/h by default).
   Fixed price: converted to IDR; with a duration, the effective monthly rate
   (total / longest stated duration in months) must be >= the monthly floor;
   without one the gig goes to needs_budget_client_review, never rejected.
   No budget, no currency or no FX rate -> review. A rate is never guessed.
2. Hard rejects: Cambodia client or work, India onsite, any onsite/local
   work, a client location restriction that excludes Indonesia, unpaid test
   tasks, pay to apply/register, payment outside the platform, cheque /
   crypto / gift-card payment, moving to Telegram/WhatsApp before a contract,
   requests for ID/passport/bank login, account rental, fake reviews, app
   store fraud, gambling or scam apps, senior/lead or large-team gigs, no
   Flutter/mobile work.
3. Manual safety review: unverified payment method, a new client (0 hires,
   no spend), vague scope with a high budget, urgency pressure, off-platform
   contact details in the post, instruction-like text aimed at an AI.
4. Ranking: Flutter relevance -> junior fit -> client quality -> rate vs
   floor -> competition (fewer proposals first) -> freshness.

Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_rates import DEFAULT_CACHE, FxTable, load_rates  # noqa: E402
from job_dedup import canonical_url  # noqa: E402
from job_rules import (  # noqa: E402
    CAMBODIA_PLACES,
    INDIA_PLACES,
    INJECTION,
    SAFETY_REJECT,
    SALARY_FLOOR_IDR_MONTHLY,
    UNPAID,
    country_code,
    norm_date,
    relevance,
    seniority_check,
)
from posting_guard import guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
TRACKER = ROOT / "freelance_tracker.csv"

HOURS_PER_MONTH = 173
SECTIONS = ("good_fits", "needs_budget_client_review", "manual_safety_review", "rejected")

# ---------------------------------------------------------------- patterns

ONSITE = re.compile(
    r"\b(on-?site\s+(?:only|work|role|position|required)|work\s+(?:from|at|in)\s+our\s+office|in[- ]office|"
    r"office[- ]based|must\s+(?:be\s+able\s+to\s+)?(?:come|commute)\s+to|must\s+relocate|local\s+candidates\s+only)\b",
    re.I,
)
LOCATION_ONLY = re.compile(
    r"\b(?:(?:us|u\.s\.|usa|uk|eu|europe|india|pakistan|canada|australia|philippines)(?:[- ]based)?\s+(?:freelancers?\s+|candidates?\s+|residents?\s+)?only|"
    r"only\s+(?:freelancers?|candidates?|applicants?|developers?)\s+(?:located|based|residing)\s+in\s+(?:the\s+)?([a-z .]+?)(?:[.,;:!]|\s+may|\s+can|\s+will|$)|"
    r"must\s+be\s+(?:located|based|residing)\s+in\s+(?:the\s+)?([a-z .]+?)(?:[.,;:!]|\s+to|\s+and|$))",
    re.I,
)
INDONESIA_OK = re.compile(r"\b(indonesia|asia|southeast\s+asia|sea|apac|worldwide|anywhere|global)\b", re.I)
LARGE_TEAM = re.compile(
    r"\b(lead\s+(?:a|our|the)\s+(?:\w+\s+)?team|team\s+lead|manage\s+(?:a|our|the)\s+team|large\s+team|"
    r"agency\s+(?:only|with\s+\d+\+?\s+developers)|team\s+of\s+(?:[5-9]|\d{2,})\+?\s+(?:developers|engineers))\b",
    re.I,
)

HARD_REJECT: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:unpaid|free)\s+(?:test|trial|sample)\s+(?:task|project|work|assignment)|\btest\s+task\s+(?:is\s+)?(?:unpaid|not\s+paid|free\s+of\s+charge)|"
                r"(?:complete|do)\s+(?:a\s+)?(?:small\s+)?(?:test|sample|trial)\b.{0,40}\b(?:for\s+free|without\s+pay(?:ment)?|unpaid)", re.I),
     "unpaid test task"),
    (re.compile(r"\b(?:pay|deposit|transfer)\s+(?:a\s+)?(?:small\s+)?(?:fee\s+|deposit\s+)?(?:to|before\s+you\s+can)\s+(?:apply|register|join|unlock|start|get\s+(?:the|this)\s+(?:job|project|gig))|"
                r"(?:registration|application|membership|joining|onboarding|activation)\s+fee", re.I),
     "pay to apply / register"),
    (re.compile(r"\b(?:pay(?:ment)?|paid)\s+(?:you\s+)?(?:directly\s+)?(?:outside|off)\s+(?:of\s+)?(?:the\s+)?(?:platform|upwork|freelancer|site|app)|"
                r"(?:avoid|skip|bypass|save)\s+(?:the\s+)?(?:upwork|freelancer|platform|service)\s+(?:fees?|commission)|"
                r"pay\s+(?:you\s+)?(?:directly|via\s+paypal|via\s+wise|by\s+bank\s+transfer)\s+(?:instead|outside)", re.I),
     "payment outside the platform"),
    (re.compile(r"\b(?:pay(?:ment)?|paid|compensat\w*)\W+(?:\w+\W+){0,4}?(?:cheque|check\s+payment|crypto\w*|bitcoin|btc|usdt|ethereum|gift\s*cards?)\b|"
                r"\b(?:cheque|crypto\w*|bitcoin|usdt|gift\s*cards?)\s+(?:as\s+)?payment\b", re.I),
     "cheque / crypto / gift-card payment"),
    (re.compile(r"\b(?:contact|message|text|reach|add|talk\s+to|dm|chat\s+with|ping)\s+(?:me|us)\s+(?:directly\s+)?(?:on|via|at|through|in)\s+(?:telegram|whatsapp|wa\b|signal|wechat|skype|discord)|"
                r"(?:move|continue|switch|take)\s+(?:the\s+|this\s+|our\s+)?(?:conversation|chat|discussion|communication)\s+to\s+(?:telegram|whatsapp|skype|discord|signal)|"
                r"\bt\.me/\S+|\bwa\.me/\S+", re.I),
     "asks to move to Telegram/WhatsApp before a contract"),
    (re.compile(r"\b(?:send|share|provide|upload|give)\s+(?:me\s+|us\s+)?(?:a\s+)?(?:copy\s+of\s+|photo\s+of\s+|scan\s+of\s+)?(?:your\s+)?(?:passport|national\s+id|id\s+card|ktp|nik|selfie\s+with\s+(?:your\s+)?id)|"
                r"\bbank(?:ing)?\s+(?:login|password|credentials|account\s+access|app\s+access)|(?:share|give|send)\s+(?:me\s+|us\s+)?(?:your\s+)?(?:online\s+)?banking\s+(?:login|password|pin)", re.I),
     "asks for ID / passport / bank login"),
    (re.compile(r"\b(?:use|rent|borrow|share|lend)\s+(?:my|your|our)\s+(?:upwork|freelancer|fiverr|toptal)\s+(?:account|profile)|"
                r"\baccount\s+(?:rental|renting|for\s+rent|sharing)|work\s+(?:under|from|through)\s+my\s+(?:upwork\s+|freelancer\s+)?(?:account|profile)|"
                r"(?:rent|buy)\s+(?:your\s+)?(?:upwork|freelancer|fiverr)\s+(?:account|profile)", re.I),
     "account rental"),
    (re.compile(r"\b(?:fake|paid|incentivi[sz]ed|bought)\s+(?:app\s+)?(?:reviews?|ratings?|installs?|downloads?)|"
                r"(?:write|post|leave|give)\s+(?:\d+\s+)?(?:positive\s+|5[- ]star\s+|good\s+)?reviews?\s+(?:for|on|to)\s+(?:our|my|the)\s+(?:app|product|listing|store)|"
                r"boost\s+(?:our\s+|my\s+)?(?:app\s+)?(?:ratings?|reviews?)", re.I),
     "fake reviews"),
    (re.compile(r"\b(?:bypass|evade|circumvent|trick|get\s+around)\s+(?:the\s+)?(?:app\s+store|play\s+store|google\s+play|apple)\s*(?:review|policy|policies|rules)?|"
                r"(?:publish|upload|release)\s+(?:it\s+)?(?:under|using|on)\s+(?:your|someone\s+else'?s|a\s+rented)\s+(?:developer\s+|play\s+console\s+|apple\s+)?account|"
                r"(?:rent|lend|sell)\s+(?:me\s+)?(?:your\s+)?(?:google\s+play|play\s+console|apple)\s+developer\s+account|\bcloaking\b|"
                r"(?:re-?skin|clone)\s+(?:of\s+)?(?:an?\s+)?(?:existing|banned|removed)\s+app", re.I),
     "app store fraud"),
    (re.compile(r"\b(?:casino|gambling|betting|judi|togel|slot\s+(?:machine|game)s?|real[- ]money\s+poker)\s+(?:app|game|platform|site)|"
                r"\b(?:ponzi|pyramid\s+scheme|investment\s+scam|fake\s+(?:bank|wallet|exchange|loan)\s+app|pinjol\s+ilegal|illegal\s+loan|phishing|"
                r"spy\s*ware|stalker\s*ware|keylogger)\b|(?:crypto|forex)\s+(?:investment|trading)\s+(?:app|platform)\s+(?:with\s+)?(?:guaranteed|fixed)\s+(?:daily\s+)?returns", re.I),
     "gambling or scam app"),
]
URGENCY = re.compile(r"\b(urgent(?:ly)?|asap|immediately|right\s+now|today\s+only|within\s+(?:24|48)\s*h(?:ours?)?|start\s+now)\b", re.I)
CONTACT = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?:\+|\b00)\d[\d\s().-]{8,}\d|\b(?:telegram|whatsapp|skype|discord)\s*(?:id|:|@)|@[A-Za-z0-9_]{4,}\b",
    re.I,
)
EXPERIENCE = re.compile(r"experience level:\s*(\w+)", re.I)


# ---------------------------------------------------------------- helpers

def gig_text(gig: dict) -> str:
    return "\n".join(str(gig.get(k) or "") for k in ("title", "description")) + "\n" + " ".join(map(str, gig.get("skills") or []))


def hourly_floor(monthly_floor: float, hours: float) -> float:
    return monthly_floor / hours


UNIT_MONTHS = {"hour": 1 / HOURS_PER_MONTH, "day": 1 / 30, "week": 7 / 30, "month": 1.0, "year": 12.0}
DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|to|–)?\s*(\d+(?:\.\d+)?)?\s*(hour|day|week|month|year|hari|minggu|bulan|tahun)s?\b", re.I)
ID_UNITS = {"hari": "day", "minggu": "week", "bulan": "month", "tahun": "year"}


def months_from_duration(text: str | None) -> float | None:
    """The longest duration a gig states, in months (conservative: lowest effective rate).

    "Less than 1 month" -> 1, "1 to 3 months" -> 3, "3 days" -> 0.1.
    Open-ended ("more than 6 months", "ongoing") and unparseable text -> None.
    """
    if not text:
        return None
    t = str(text).lower()
    if re.search(r"\b(more\s+than|over|ongoing|long[- ]term|indefinite)\b", t) and not re.search(r"\bless\s+than\b", t):
        return None
    best = None
    for m in DURATION.finditer(t):
        unit = ID_UNITS.get(m.group(3).lower(), m.group(3).lower())
        value = float(m.group(2) or m.group(1)) * UNIT_MONTHS[unit]
        best = value if best is None else max(best, value)
    return best


def rate_check(gig: dict, fx: FxTable | None, monthly_floor: float = SALARY_FLOOR_IDR_MONTHLY, hours: float = HOURS_PER_MONTH) -> dict:
    """Rule 1. status: pass | reject | needs_budget_review."""
    floor_h = hourly_floor(monthly_floor, hours)
    btype = gig.get("budget_type")
    lo, hi, cur = gig.get("budget_min"), gig.get("budget_max"), gig.get("budget_currency")
    out = {"status": "needs_budget_review", "reason": "", "idr_hourly": None, "idr_monthly_effective": None, "idr_total": None,
           "ratio_to_floor": None, "fx_rate": None, "fx_date": None, "fx_stale": False,
           "floor_idr_hourly": round(floor_h), "floor_idr_monthly": monthly_floor}
    if lo is None and hi is None:
        out["reason"] = "budget not stated"
        return out
    if btype not in ("hourly", "fixed"):
        out["reason"] = "budget type (hourly or fixed) not stated"
        return out
    if not cur:
        out["reason"] = "budget currency not stated"
        return out
    rate = 1.0 if str(cur).upper() == "IDR" else (fx.idr_per_unit(cur) if fx else None)
    if rate is None:
        out["reason"] = f"no exchange rate for {cur} (no fetch and no cache)"
        return out
    if str(cur).upper() != "IDR" and fx:
        out.update(fx_rate=round(rate, 6), fx_date=fx.fetched_on, fx_stale=fx.stale)
    stale = f" (rate from cache dated {fx.fetched_on}; refresh failed)" if fx and fx.stale and str(cur).upper() != "IDR" else ""
    amount = float(lo if lo is not None else hi)
    only_max = lo is None
    if btype == "hourly":
        idr_h = amount * rate
        out.update(idr_hourly=round(idr_h), ratio_to_floor=round(idr_h / floor_h, 3))
        if idr_h >= floor_h:
            out.update(status="needs_budget_review" if only_max else "pass",
                       reason=(f"only a maximum is stated (IDR {idr_h:,.0f}/h)" if only_max else f"IDR {idr_h:,.0f}/h >= IDR {floor_h:,.0f}/h floor") + stale)
        else:
            out.update(status="reject", reason=f"IDR {idr_h:,.0f}/h is below the IDR {floor_h:,.0f}/h floor" + stale)
        return out
    total = amount * rate
    out["idr_total"] = round(total)
    months = months_from_duration(gig.get("est_duration"))
    if months is None:
        out["reason"] = f"fixed price IDR {total:,.0f} with no usable duration; judge the scope before bidding" + stale
        return out
    monthly = total / months
    out.update(idr_monthly_effective=round(monthly), ratio_to_floor=round(monthly / monthly_floor, 3))
    if monthly >= monthly_floor:
        out.update(status="pass", reason=f"IDR {total:,.0f} over {gig.get('est_duration')} = IDR {monthly:,.0f}/month >= floor" + stale)
    else:
        out.update(status="reject", reason=f"IDR {total:,.0f} over {gig.get('est_duration')} = IDR {monthly:,.0f}/month, below the IDR {monthly_floor:,.0f} floor" + stale)
    return out


def location_check(gig: dict) -> list[str]:
    """Hard rejects about where the client is or where the work happens."""
    reasons = []
    text = gig_text(gig)
    evidence = " ".join(map(str, gig.get("evidence") or []))
    client = str(gig.get("client_country") or "")
    code = country_code({"country": client}) if client else None
    if code == "KH" or CAMBODIA_PLACES.search(client) or CAMBODIA_PLACES.search(text):
        reasons.append("Cambodia-based client or work (deal-breaker)")
    onsite = bool(ONSITE.search(text)) or "onsite:" in evidence
    if onsite and (code == "IN" or INDIA_PLACES.search(text)):
        reasons.append("India onsite (deal-breaker)")
    elif onsite:
        reasons.append("onsite / local work, not remote")
    allowed = [str(c) for c in (gig.get("freelancer_locations") or []) if c]
    if allowed and not any(INDONESIA_OK.search(c) or country_code({"country": c}) == "ID" for c in allowed):
        reasons.append(f"client accepts freelancers only from {', '.join(allowed)}")
    for m in LOCATION_ONLY.finditer(text):
        place = (m.group(1) or m.group(2) or m.group(0)).strip()
        if not INDONESIA_OK.search(place):
            reasons.append(f"location restriction excludes Indonesia: \"{m.group(0).strip()[:60]}\"")
            break
    return reasons


def junior_check(gig: dict) -> dict:
    level = EXPERIENCE.search(" ".join(map(str, gig.get("evidence") or [])))
    seniority = {"EXPERT": "senior", "ENTRY_LEVEL": "junior"}.get(level.group(1).upper(), "") if level else ""
    out = seniority_check({"title": gig.get("title"), "description": gig.get("description"), "seniority": seniority})
    if out["fit"] != "reject" and LARGE_TEAM.search(gig_text(gig)):
        out = {"fit": "reject", "reason": "asks to lead or work in a large team", "years": out.get("years")}
    return out


def client_score(gig: dict) -> float:
    """0-10. Verified payment, hires, rating, spend. Unknown fields add nothing."""
    score = 0.0
    if gig.get("client_verified_payment") is True:
        score += 3
    hires = gig.get("client_hires")
    if isinstance(hires, (int, float)) and hires > 0:
        score += min(hires, 20) / 20 * 2.5
    rating = gig.get("client_rating")
    if isinstance(rating, (int, float)) and rating > 0:
        score += min(rating, 5) / 5 * 2.5
    spent = gig.get("client_total_spent")
    if isinstance(spent, (int, float)) and spent > 0:
        score += min(math.log10(spent + 1), 5) / 5 * 2
    return round(score, 2)


def safety_check(gig: dict, rate: dict) -> dict:
    text = gig_text(gig)
    reject = [label for rx, label in HARD_REJECT if rx.search(text)]
    reject += [f"safety: {label}" for rx, label in SAFETY_REJECT if rx.search(text)]
    if UNPAID.search(text):
        reject.append("unpaid work")
    review = []
    if gig.get("client_verified_payment") is False:
        review.append("client payment method not verified")
    if gig.get("client_hires") == 0 and not gig.get("client_total_spent"):
        review.append("new client: 0 hires and no spend")
    big = (rate.get("idr_total") or 0) >= 30_000_000 or (rate.get("idr_hourly") or 0) >= 800_000
    if big and len(str(gig.get("description") or "")) < 300:
        review.append("vague scope with a high budget")
    if URGENCY.search(text):
        review.append("urgency pressure")
    if CONTACT.search(str(gig.get("description") or "")):
        review.append("off-platform contact details in the post")
    cleaned, findings = guard(text, "text")
    if findings.get("instruction_like") or findings.get("invisible_flagged") or findings.get("invisible_text") or INJECTION.search(text):
        review.append("instruction-like text aimed at an AI (prompt injection suspected); ignored")
    # Low concern needs no signals AND platform data showing a payment-verified client (escrow applies).
    clean_api = gig.get("source_type") == "api" and gig.get("client_verified_payment") is True
    status = ("rejected_safety_risk" if reject else "high_risk_manual_review" if review
              else "verified_low_concern" if clean_api else "verification_pending")
    return {"status": status, "reject": reject, "review": review, "guard_verdict": findings.get("verdict")}


# ---------------------------------------------------------------- tracker and dedup

def proposed_keys(tracker: Path | None) -> set[str]:
    """platform:gig_id and canonical URLs already in freelance_tracker.csv."""
    keys: set[str] = set()
    if not tracker or not tracker.is_file():
        return keys
    with tracker.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("platform") and row.get("gig_id"):
                keys.add(f"{row['platform'].strip().lower()}:{row['gig_id'].strip()}")
            if row.get("url"):
                keys.add(canonical_url(row["url"]) or row["url"])
    return keys


def gig_keys(gig: dict) -> list[str]:
    keys = []
    if gig.get("platform") and gig.get("gig_id"):
        keys.append(f"{str(gig['platform']).strip().lower()}:{str(gig['gig_id']).strip()}")
    if gig.get("url"):
        keys.append(canonical_url(gig["url"]) or gig["url"])
    return keys


def dedupe(gigs: list[dict]) -> tuple[list[dict], int]:
    """One record per gig (platform+id or canonical URL); an API record beats a search lead."""
    kept: list[dict] = []
    index: dict[str, int] = {}
    dropped = 0
    for gig in gigs:
        hit = next((index[k] for k in gig_keys(gig) if k in index), None)
        if hit is None:
            index.update({k: len(kept) for k in gig_keys(gig)})
            kept.append(gig)
            continue
        dropped += 1
        if kept[hit].get("source_type") == "search_lead" and gig.get("source_type") == "api":
            kept[hit] = gig
        index.update({k: hit for k in gig_keys(gig)})
    return kept, dropped


# ---------------------------------------------------------------- evaluate

JUNIOR_ORDER = {"junior": 0, "unspecified": 1, "stretch": 2, "reject": 3}


def evaluate_gig(gig: dict, fx: FxTable | None, today: date, *, monthly_floor: float = SALARY_FLOOR_IDR_MONTHLY,
                 hours: float = HOURS_PER_MONTH, proposed: set[str] | None = None) -> dict:
    rejected: list[str] = []
    review_budget: list[str] = []
    rel = relevance({"title": gig.get("title"), "description": gig_text(gig)})
    junior = junior_check(gig)
    rate = rate_check(gig, fx, monthly_floor, hours)
    safety = safety_check(gig, rate)

    rejected += location_check(gig)
    if rel == 0:
        rejected.append("no Flutter/mobile work (off target)")
    if junior["fit"] == "reject":
        rejected.append(junior["reason"])
    if rate["status"] == "reject":
        rejected.append(f"rate floor: {rate['reason']}")
    rejected += safety["reject"]
    if rate["status"] == "needs_budget_review":
        review_budget.append(f"budget: {rate['reason']}")
    if gig.get("source_type") == "search_lead":
        review_budget.append("search-engine lead: client, budget and country restrictions unverified - open the gig and paste it into /propose")
    elif gig.get("client_verified_payment") is None and gig.get("client_hires") is None:
        review_budget.append("client history not available from this platform")
    already = bool(proposed and any(k in proposed for k in gig_keys(gig)))

    if rejected:
        section = "rejected"
    elif safety["review"]:
        section = "manual_safety_review"
    elif review_budget:
        section = "needs_budget_client_review"
    else:
        section = "good_fits"
    posted = norm_date(gig.get("posted_at"))
    age = (today - posted).days if posted else 999
    proposals = gig.get("proposals_count")
    rank_key = [-rel, JUNIOR_ORDER.get(junior["fit"], 1), -client_score(gig), -(rate.get("ratio_to_floor") or 0),
                proposals if isinstance(proposals, (int, float)) else 999, age]
    return {
        "section": section,
        "reasons": rejected if section == "rejected" else safety["review"] if section == "manual_safety_review" else review_budget,
        "budget_notes": review_budget,
        "relevance": rel,
        "junior_fit": junior["fit"],
        "junior_reason": junior["reason"],
        "client_score": client_score(gig),
        "rate": rate,
        "safety_screening": safety["status"],
        "safety_review": safety["review"],
        "guard_verdict": safety["guard_verdict"],
        "already_proposed": already,
        "rank_key": rank_key,
    }


def load_platforms(path: Path | None = None) -> dict:
    try:
        return json.loads((path or DATA / "freelance_platforms.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate(gigs: list[dict], fx: FxTable | None, today: date, *, monthly_floor: float = SALARY_FLOOR_IDR_MONTHLY,
             hours: float = HOURS_PER_MONTH, tracker: Path | None = TRACKER) -> dict:
    unique, dropped = dedupe(gigs)
    proposed = proposed_keys(tracker)
    sections: dict[str, list] = {s: [] for s in SECTIONS}
    for gig in unique:
        rules = evaluate_gig(gig, fx, today, monthly_floor=monthly_floor, hours=hours, proposed=proposed)
        sections[rules["section"]].append({**gig, "safety_screening": rules["safety_screening"], "rules": rules})
    for name in SECTIONS:
        sections[name].sort(key=lambda g: g["rules"]["rank_key"])
    registry = load_platforms()
    return {
        "sections": sections,
        "vetted_networks": registry.get("vetted_networks", []),
        "platforms": registry.get("platforms", []),
        "duplicates_dropped": dropped,
        "counts": {s: len(v) for s, v in sections.items()},
        "fx": {"date": fx.fetched_on if fx else None, "stale": fx.stale if fx else None, "source": fx.source if fx else None},
        "config": {"monthly_floor_idr": monthly_floor, "hours_per_month": hours, "hourly_floor_idr": round(hourly_floor(monthly_floor, hours))},
    }


def read_gigs_text(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict) and "runs" in data:
        return [g for run in data["runs"] for g in (run.get("results") or [])]
    if isinstance(data, dict):
        data = data.get("results", [data])
    if not isinstance(data, list):
        raise ValueError("input must be a JSON array of gigs, {results: [...]} or {runs: [...]}")
    return data


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Deterministic rules for freelance gigs")
    parser.add_argument("command", choices=["evaluate"])
    parser.add_argument("--in", dest="inp", required=True, help="gigs JSON file, or - for stdin")
    parser.add_argument("--fx-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true", help="never fetch exchange rates; cache only")
    parser.add_argument("--today", help="YYYY-MM-DD (tests)")
    parser.add_argument("--monthly-floor", type=float, default=SALARY_FLOOR_IDR_MONTHLY, help="IDR per month (default 5,000,000)")
    parser.add_argument("--hours-per-month", type=float, default=HOURS_PER_MONTH, help="hours that make a month (default 173)")
    parser.add_argument("--tracker", type=Path, default=TRACKER)
    args = parser.parse_args(argv)
    if args.monthly_floor <= 0 or args.hours_per_month <= 0:
        parser.error("--monthly-floor and --hours-per-month must be positive")
    try:
        gigs = read_gigs_text(sys.stdin.read() if args.inp == "-" else Path(args.inp).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "code": "BAD_INPUT"}), file=sys.stderr)
        return 1
    today = date.fromisoformat(args.today) if args.today else date.today()
    fx = load_rates(args.fx_cache, today, offline=args.offline)
    print(json.dumps(evaluate(gigs, fx, today, monthly_floor=args.monthly_floor, hours=args.hours_per_month, tracker=args.tracker),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
