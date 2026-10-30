#!/usr/bin/env python3
"""Deterministic hard rules for the global junior-Flutter search.

These checks are code, not model judgment, so a persuasive posting cannot talk
its way past them. /scrape tags jobs with them and /rank sorts its report by
them; the fit scoring in 04-job-evaluation.md runs on top and can never
override a hard-rule rejection.

Run from the repo root:
    python tools/job_rules.py evaluate --in <jobs.json> [--offline] [--today YYYY-MM-DD]

<jobs.json> is a JSON array (or {"results": [...]}) of job records - portal CLI
output or seen_jobs entries. Output: {"sections": {"confirmed", "needs_verification",
"manual_safety_review", "rejected"}, "needs_login": {portal: [...]}, "counts", "fx"}.
Each job comes back with `rules` (verdict, reasons, flags, salary check,
safety_screening, apply_method, eligibility, seniority, relevance, rank_key).

Rules (from the user's brief; the profile files carry the prose version):
1. Cambodia-based jobs: always rejected.
2. India onsite/hybrid: always rejected; India remote only if rule 3 passes.
3. Salary floor for every job everywhere: minimum monthly pay converted to IDR
   must be strictly greater than IDR 5,000,000. Undisclosed or unclear
   (currency/period) -> needs_salary_verification; foreign-currency pay within
   +/-5% of the floor -> needs_salary_verification (rates move); IDR pay has no
   FX band, so exactly 5,000,000 is rejected. Never inferred from reputation.
4. Safety screening is separate from fit: verified_low_concern |
   verification_pending | high_risk_manual_review | rejected_safety_risk | unknown.
5. Ranking: Flutter/mobile relevance -> junior fit -> full-time/paid contract ->
   work eligibility -> remote eligibility -> visa/relocation -> pay vs cost of
   living -> employer credibility -> freshness -> evidence quality, with
   anything not verified_low_concern never outranking a verified job.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_rates import DEFAULT_CACHE, FxTable, load_rates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"

SALARY_FLOOR_IDR_MONTHLY = 5_000_000
BORDERLINE_BAND = 0.05

SAFETY_STATUSES = (
    "verified_low_concern",
    "verification_pending",
    "high_risk_manual_review",
    "rejected_safety_risk",
    "unknown",
)
SECTIONS = ("confirmed", "needs_verification", "manual_safety_review", "rejected")
APPLY_METHODS = ("ats_form", "portal_login", "email", "external_unknown")

# Ranking/priority countries (ranking only, never a filter).
PRIORITY_COUNTRIES = {
    "US", "CA", "GB", "IE", "DE", "NL", "CH", "AT", "BE", "LU", "DK", "SE", "NO", "FI", "IS",
    "SG", "AU", "NZ", "JP", "KR", "MY", "PH", "TH", "VN", "ID", "BN", "TL",
}

COUNTRY_NAMES = {
    "indonesia": "ID", "cambodia": "KH", "kampuchea": "KH", "india": "IN", "singapore": "SG",
    "malaysia": "MY", "philippines": "PH", "thailand": "TH", "vietnam": "VN", "viet nam": "VN",
    "brunei": "BN", "timor-leste": "TL", "east timor": "TL", "myanmar": "MM", "burma": "MM",
    "laos": "LA", "lao pdr": "LA", "japan": "JP", "south korea": "KR", "korea": "KR",
    "australia": "AU", "new zealand": "NZ", "united states": "US", "usa": "US", "u.s.": "US",
    "canada": "CA", "united kingdom": "GB", "uk": "GB", "england": "GB", "ireland": "IE",
    "germany": "DE", "deutschland": "DE", "netherlands": "NL", "switzerland": "CH",
    "austria": "AT", "belgium": "BE", "luxembourg": "LU", "denmark": "DK", "sweden": "SE",
    "sverige": "SE", "norway": "NO", "norge": "NO", "finland": "FI", "iceland": "IS",
    "china": "CN", "hong kong": "HK", "taiwan": "TW", "pakistan": "PK", "egypt": "EG",
}

CAMBODIA_PLACES = re.compile(
    r"\b(cambodia|kampuchea|phnom\s*penh|siem\s*reap|sihanoukville|preah\s+sihanouk|bavet|poipet|kampot|battambang)\b", re.I
)
INDIA_PLACES = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|bombay|new\s+delhi|delhi|ncr|gurgaon|gurugram|noida|hyderabad|chennai|pune|"
    r"kolkata|ahmedabad|kochi|cochin|jaipur|indore|chandigarh|coimbatore|thiruvananthapuram|trivandrum|lucknow|nagpur|"
    r"mohali|vadodara|surat|bhubaneswar|visakhapatnam|mysore|mysuru)\b",
    re.I,
)
# Enhanced screening: specific worksites with documented scam-compound activity
# (UNODC/OHCHR reports 2023-2024). Country-level matches get proportionate
# screening only - the employer and worksite are judged, not the country.
HOTSPOTS = re.compile(
    r"\b(myawaddy|shwe\s*kokko|kk\s*park|yatai|mong\s*la|tachileik|golden\s+triangle|bokeo|ton\s+pheung|"
    r"mae\s*sot|mae\s*sai|chiang\s*saen|o'?smach|bavet|poipet|sihanoukville)\b",
    re.I,
)
ENHANCED_COUNTRIES = {"MM", "LA"}
THAI_BORDER = re.compile(r"\b(mae\s*sot|mae\s*sai|chiang\s*saen|tak\s+province|three\s+pagodas|ranong)\b", re.I)


# ---------------------------------------------------------------- helpers

def text_of(job: dict, *fields: str) -> str:
    return "\n".join(str(job.get(f) or "") for f in fields)


def country_code(job: dict) -> str | None:
    """ISO code from `country`, else from a recognisable country name in `location`."""
    raw = str(job.get("country") or "").strip()
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    if raw:
        code = COUNTRY_NAMES.get(raw.lower())
        if code:
            return code
    loc = str(job.get("location") or "").lower()
    for name, code in COUNTRY_NAMES.items():
        if len(name) > 3 and re.search(rf"\b{re.escape(name)}\b", loc):
            return code
    return None


def work_mode(job: dict) -> str | None:
    """remote | hybrid | onsite | None, from the record and then the location text."""
    mode = str(job.get("work_mode") or "").lower()
    for m in ("hybrid", "remote", "onsite"):
        if m in mode or (m == "onsite" and ("on-site" in mode or "office" in mode)):
            return m
    loc = str(job.get("location") or "").lower()
    if "hybrid" in loc:
        return "hybrid"
    if re.search(r"\bremote\b", loc):
        return "remote"
    if re.search(r"\b(on-?site|office based|in office)\b", loc):
        return "onsite"
    return None


def norm_date(value) -> date | None:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- salary

CURRENCY_SYMBOLS = [
    (r"\bRp\.?\s?|\bIDR\b", "IDR"),
    (r"US\$|\bUSD\b", "USD"),
    (r"S\$|\bSGD\b", "SGD"),
    (r"A\$|\bAUD\b", "AUD"),
    (r"NZ\$|\bNZD\b", "NZD"),
    (r"C\$|CA\$|\bCAD\b", "CAD"),
    (r"HK\$|\bHKD\b", "HKD"),
    (r"€|\bEUR\b", "EUR"),
    (r"£|\bGBP\b", "GBP"),
    (r"₹|\bINR\b|\bRs\.?\s?", "INR"),
    (r"\bRM\s?|\bMYR\b", "MYR"),
    (r"₱|\bPHP\b", "PHP"),
    (r"฿|\bTHB\b", "THB"),
    (r"₫|\bVND\b", "VND"),
    (r"₩|\bKRW\b", "KRW"),
    (r"\bJPY\b|円", "JPY"),
    (r"\bCHF\b", "CHF"),
    (r"\bSEK\b|\bkr/mån", "SEK"),
    (r"\bNOK\b", "NOK"),
    (r"\bDKK\b", "DKK"),
    (r"\bISK\b", "ISK"),
    (r"\bBND\b", "BND"),
    (r"\bPKR\b", "PKR"),
    (r"\bEGP\b", "EGP"),
]
PERIOD_WORDS = [
    (r"per\s+annum|p\.?\s?a\.?\b|/\s?(?:yr|year)|\bper\s+year\b|\bannual(?:ly)?\b|\byearly\b|\btahun\b|年収|\bLPA\b", "year"),
    (r"/\s?(?:mo|month)\b|\bper\s+month\b|\bmonthly\b|\bsebulan\b|\bper\s+bulan\b|/\s?bulan|\bbulan\b|\bmån\b|月給|\bmonth\b", "month"),
    (r"/\s?(?:wk|week)\b|\bper\s+week\b|\bweekly\b", "week"),
    (r"/\s?day\b|\bper\s+day\b|\bdaily\b|\bper\s+hari\b|\bhari\b", "day"),
    (r"/\s?(?:hr|hour)\b|\bper\s+hour\b|\bhourly\b|\bper\s+jam\b|\bjam\b", "hour"),
]
NUMBER = r"(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(k|rb|ribu|jt|juta|m|mn|mio|million|lakh|lakhs|lpa)?\b"


def _to_number(raw: str, suffix: str | None) -> float | None:
    s = raw.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)  # thousands separators (6.000.000 or 6,000,000)
    else:
        s = s.replace(",", ".")
    try:
        value = float(s)
    except ValueError:
        return None
    suffix = (suffix or "").lower()
    if suffix in ("k", "rb", "ribu"):
        value *= 1_000
    elif suffix in ("jt", "juta", "m", "mn", "mio", "million"):
        value *= 1_000_000
    elif suffix in ("lakh", "lakhs", "lpa"):
        value *= 100_000
    return value


def parse_salary_text(text: str | None) -> dict | None:
    """Pull an explicit pay statement out of free text. Ambiguous symbols ($, ¥, kr)
    leave the currency None; a missing period leaves the period None."""
    if not text:
        return None
    t = str(text)
    currency = None
    cur_pos = None
    for pattern, code in CURRENCY_SYMBOLS:
        m = re.search(pattern, t)
        if m and (cur_pos is None or m.start() < cur_pos):
            currency, cur_pos = code, m.start()
    if cur_pos is None:
        return None  # numbers without any currency marker are not pay we can read
    window = t[cur_pos: cur_pos + 120]
    nums = [(m.group(1), m.group(2)) for m in re.finditer(NUMBER, window, re.I)]
    values = [v for v in (_to_number(n, s) for n, s in nums) if v is not None and v > 0]
    if not values:
        return None
    # A trailing unit applies to a bare leading number ("6-8 jt" = 6jt-8jt).
    if len(nums) >= 2 and not nums[0][1] and nums[1][1]:
        values[0] = _to_number(nums[0][0], nums[1][1]) or values[0]
    period = None
    for pattern, p in PERIOD_WORDS:
        if re.search(pattern, window, re.I):
            period = p
            break
    if re.search(r"\bLPA\b|lakhs?\s+per\s+annum", window, re.I):
        period = "year"
    lo, hi = values[0], values[1] if len(values) > 1 else None
    if hi is not None and hi < lo:
        hi = None
    gross = "net" if re.search(r"\b(net|nett|take[- ]home|bersih)\b", window, re.I) else (
        "gross" if re.search(r"\b(gross|kotor|brutto)\b", window, re.I) else None)
    return {"min": lo, "max": hi, "currency": currency, "period": period, "gross_or_net": gross, "source": "salary text"}


def monthly(amount: float, period: str) -> float | None:
    factors = {"month": 1.0, "year": 1 / 12, "week": 52 / 12, "day": 260 / 12, "hour": 40 * 52 / 12}
    f = factors.get(period)
    return amount * f if f else None


def salary_check(job: dict, fx: FxTable | None) -> dict:
    """Rule 3. status: pass | reject | needs_salary_verification."""
    mn, mx = job.get("salary_min"), job.get("salary_max")
    currency, period = job.get("salary_currency"), job.get("salary_period")
    gross = job.get("salary_gross_or_net")
    source = "structured fields"
    if mn is None and mx is None:
        parsed = parse_salary_text(job.get("salary_text")) or parse_salary_text(job.get("description"))
        if parsed:
            mn, mx, currency, period, gross, source = (
                parsed["min"], parsed["max"], parsed["currency"], parsed["period"], parsed["gross_or_net"], parsed["source"])
    out = {
        "status": "needs_salary_verification",
        "reason": "",
        "original": {"min": mn, "max": mx, "currency": currency, "period": period, "gross_or_net": gross, "source": source},
        "salary_idr_monthly_min": None,
        "fx_rate": None,
        "fx_date": None,
        "fx_stale": False,
    }
    if mn is None and mx is None:
        out["reason"] = "salary undisclosed"
        return out
    if not currency or not period:
        out["reason"] = f"salary stated but {'currency' if not currency else 'period'} unclear"
        return out
    rate = 1.0 if str(currency).upper() == "IDR" else (fx.idr_per_unit(currency) if fx else None)
    if rate is None:
        out["reason"] = f"no exchange rate available for {currency} (no fetch and no cache)"
        return out
    if str(currency).upper() != "IDR" and fx:
        out.update(fx_rate=round(rate, 6), fx_date=fx.fetched_on, fx_stale=fx.stale)
    elif str(currency).upper() == "IDR":
        out.update(fx_rate=1.0, fx_date=None)
    floor = SALARY_FLOOR_IDR_MONTHLY
    if mn is None:
        # "Up to X": the minimum is unknown. Only a maximum at or under the floor decides.
        top = monthly(float(mx), period) * rate
        if top <= floor * (1 - (BORDERLINE_BAND if str(currency).upper() != "IDR" else 0)):
            out.update(status="reject", reason=f"maximum pay IDR {top:,.0f}/month is not above the IDR {floor:,} floor")
        else:
            out["reason"] = "only a maximum is stated; the minimum must exceed the floor"
        return out
    idr = monthly(float(mn), period) * rate
    out["salary_idr_monthly_min"] = round(idr)
    if str(currency).upper() == "IDR":
        if idr > floor:
            out.update(status="pass", reason=f"IDR {idr:,.0f}/month > floor")
        else:
            out.update(status="reject", reason=f"IDR {idr:,.0f}/month is not above the IDR {floor:,} floor")
        return out
    if idr <= floor * (1 - BORDERLINE_BAND):
        out.update(status="reject", reason=f"~IDR {idr:,.0f}/month after conversion is below the IDR {floor:,} floor")
    elif idr < floor * (1 + BORDERLINE_BAND):
        out.update(status="needs_salary_verification", reason=f"~IDR {idr:,.0f}/month is within 5% of the floor; exchange rates move")
    else:
        out.update(status="pass", reason=f"~IDR {idr:,.0f}/month after conversion > floor")
    if out["fx_stale"]:
        out["reason"] += f" (rate from cache dated {fx.fetched_on}; refresh failed)"
    return out


# ---------------------------------------------------------------- role checks

INTERN_TITLE = re.compile(
    r"\b(intern|interns|internship|magang|praktikum|praktikant|werkstudent|working\s+student|student\s+(?:job|assistant|worker|placement)|"
    r"co-?op\b|trainee(?:ship)?|apprentice(?:ship)?|ojt|pkl|summer\s+student|28卒|27卒|新卒インターン)",
    re.I,
)
INTERN_BODY = re.compile(
    r"\b(this\s+is\s+an?\s+(?:paid\s+|unpaid\s+)?internship|internship\s+(?:program(?:me)?|position|role|period)|"
    r"intern[- ]to[- ]hire|\d+[- ]month\s+internship|program\s+magang|student\s+placement|"
    r"must\s+be\s+(?:a\s+)?(?:current(?:ly)?\s+)?(?:enrolled\s+)?student)",
    re.I,
)
TRAINING_PROGRAM = re.compile(
    r"\b(bootcamp|training\s+program(?:me)?|(?:pay|fee)\s+(?:for|to\s+join)\s+(?:the\s+)?(?:training|course)|"
    r"course\s+fee|tuition|ikatan\s+dinas|trainee\s+program(?:me)?)",
    re.I,
)
UNPAID = re.compile(r"\b(unpaid|volunteer(?:ing)?\s+(?:role|position)|no\s+salary|equity[- ]only|tanpa\s+gaji|without\s+pay)\b", re.I)
SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head|architect|manager|director|vp|chief|expert|tech\s*lead)\b", re.I
)
JUNIOR_TITLE = re.compile(r"\b(junior|jr\.?|entry[- ]level|graduate|associate|fresh\s*graduate|fresher|new\s+grad)\b", re.I)
YEARS = re.compile(
    r"(?:(?:minimum|min\.?|at\s+least|minimal)\s+)?(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to|~)?\s*(\d{1,2})?\s*\+?\s*"
    r"(?:years?|yrs?|tahun|jahre?|år|vuotta|年)",
    re.I,
)
FLUTTER = re.compile(r"\b(flutter|dart)\b", re.I)
MOBILE = re.compile(
    r"\b(mobile|android|ios|swift|kotlin|react\s+native|cross[- ]platform|app\s+developer|apputvikler|apputvecklare|mobilutvikler|"
    r"aplikasi\s+mobile|モバイル)\b",
    re.I,
)


def required_years(job: dict) -> int | None:
    """Smallest explicit 'N years' requirement, from required_experience then the description."""
    for field in ("required_experience", "description"):
        text = str(job.get(field) or "")
        found = [int(m.group(1)) for m in YEARS.finditer(text) if int(m.group(1)) <= 20]
        if found:
            return min(found)
    return None


def seniority_check(job: dict) -> dict:
    title = str(job.get("title") or "")
    years = required_years(job)
    stated = str(job.get("seniority") or "")
    senior_title = bool(SENIOR_TITLE.search(title)) or bool(re.search(r"\b(senior|lead|principal|staff|mid-senior)\b", stated, re.I))
    junior_title = bool(JUNIOR_TITLE.search(title)) or bool(re.search(r"\b(junior|entry|graduate|intern)\b", stated, re.I))
    if years is not None and years >= 4:
        return {"fit": "reject", "reason": f"requires {years}+ years of experience (not a junior role)", "years": years}
    if senior_title and (years is None or years >= 3) and not junior_title:
        return {"fit": "reject", "reason": "senior/lead role by title", "years": years}
    if years == 3:
        return {"fit": "stretch", "reason": "asks for 3 years (stretch for a junior profile)", "years": years}
    if junior_title or (years is not None and years <= 2):
        return {"fit": "junior", "reason": "junior/entry level by title or experience", "years": years}
    return {"fit": "unspecified", "reason": "level not stated", "years": years}


def employment_check(job: dict) -> dict:
    title, body = str(job.get("title") or ""), str(job.get("description") or "")
    etype = str(job.get("employment_type") or "")
    if INTERN_TITLE.search(title) or INTERN_TITLE.search(etype) or INTERN_BODY.search(body):
        return {"type": "internship", "reject": "internship / student placement (deal-breaker)"}
    if TRAINING_PROGRAM.search(title) or TRAINING_PROGRAM.search(body[:3000]):
        return {"type": "training", "reject": "bootcamp or training program, not a job"}
    if UNPAID.search(title) or UNPAID.search(body):
        return {"type": "unpaid", "reject": "unpaid role (deal-breaker)"}
    e = etype.lower()
    if re.search(r"full|permanent|fast|vanlig|heltid|tetap|regular", e):
        return {"type": "full_time", "reject": None}
    if re.search(r"contract|freelance|contractor|temporary|kontrak|fixed", e):
        return {"type": "contract", "reject": None}
    if re.search(r"part", e):
        return {"type": "part_time", "reject": None}
    return {"type": "unknown", "reject": None}


def relevance(job: dict) -> int:
    title, body = str(job.get("title") or ""), str(job.get("description") or "")
    if FLUTTER.search(title):
        return 3
    if MOBILE.search(title) and FLUTTER.search(body):
        return 2
    if MOBILE.search(title) or FLUTTER.search(body):
        return 1
    return 0


# ---------------------------------------------------------------- location & eligibility

ELIGIBLE_ID = re.compile(
    r"\b(indonesia|southeast\s+asia|south-east\s+asia|sea\b|asean|apac|asia(?:-pacific)?|worldwide|anywhere|global(?:ly)?|"
    r"all\s+countries|any\s+(?:country|location)|international)\b",
    re.I,
)
VISA_POSITIVE = re.compile(
    r"(visa\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)|we\s+(?:can\s+|will\s+)?sponsor|"
    r"sponsor(?:ship)?\s+(?:your|a|the)\s+(?:work\s+)?visa|relocation\s+(?:support|package|assistance|bonus)|"
    r"help\s+(?:you\s+)?(?:with\s+)?(?:the\s+)?(?:visa|relocation)|blue\s+card\s+support)",
    re.I,
)
VISA_NEGATIVE = re.compile(
    r"(no\s+visa\s+sponsorship|(?:not|unable\s+to|cannot|can't|won't|will\s+not)\s+(?:provide\s+)?sponsor|"
    r"without\s+(?:visa\s+)?sponsorship|must\s+(?:already\s+)?(?:have|hold)\s+(?:the\s+)?(?:right|authori[sz]ation|eligibility)\s+to\s+work|"
    r"must\s+be\s+(?:legally\s+)?(?:authori[sz]ed|eligible)\s+to\s+work|(?:citizens?|permanent\s+residents?)\s+only|"
    r"only\s+(?:open\s+to\s+)?(?:candidates|applicants)\s+(?:based|located|residing)\s+in)",
    re.I,
)


def location_check(job: dict) -> dict:
    """Rules 1 and 2 plus work eligibility for an Indonesian applicant."""
    code = country_code(job)
    mode = work_mode(job)
    loc_text = text_of(job, "location", "country", "remote_eligibility")
    out: dict = {"country": code, "work_mode": mode, "reject": None, "eligibility": "unknown", "remote_eligibility": "unknown", "visa": "none_stated"}
    if code == "KH" or CAMBODIA_PLACES.search(loc_text):
        out["reject"] = "Cambodia-based job (hard rule 1)"
        return out
    india = code == "IN" or bool(INDIA_PLACES.search(str(job.get("location") or "")))
    if india and mode != "remote":
        out["reject"] = "India onsite/hybrid job (hard rule 2)" if mode else "India job with no stated remote arrangement (hard rule 2: only remote India jobs are allowed)"
        return out
    body = text_of(job, "description", "visa_sponsorship", "relocation")
    if VISA_NEGATIVE.search(body):
        out["visa"] = "negative"
    elif VISA_POSITIVE.search(body) or (job.get("visa_sponsorship") and "unconfirmed" not in str(job.get("visa_sponsorship"))):
        out["visa"] = "positive"
    elif job.get("visa_sponsorship"):
        out["visa"] = "portal_tag"
    if mode == "remote":
        elig = str(job.get("remote_eligibility") or "")
        if not elig or elig.lower() in ("remote", "no location restriction listed", "remote (no location restriction listed)"):
            out["remote_eligibility"] = "unknown"
        elif ELIGIBLE_ID.search(elig):
            out["remote_eligibility"] = "eligible_explicit"
        else:
            out["remote_eligibility"] = "restricted"
            out["reject"] = f"remote role restricted to: {elig[:120]}"
            return out
        out["eligibility"] = out["remote_eligibility"]
        if out["visa"] == "negative":
            # "Must be authorized to work in X" on a remote role means remote-from-X.
            out["reject"] = "remote role requires existing work authorisation in another country"
        return out
    if code == "ID":
        out["eligibility"] = "eligible_citizen"
        return out
    if out["visa"] == "negative":
        out["reject"] = "requires existing work authorisation; no sponsorship"
        return out
    out["eligibility"] = "visa_evidence" if out["visa"] == "positive" else "needs_visa"
    return out


# ---------------------------------------------------------------- safety

SAFETY_REJECT = [
    (re.compile(r"(passport\s+(?:will\s+be\s+)?(?:kept|held|retained|surrendered|collected)|(?:hold|keep|retain)\s+(?:your\s+)?passport)", re.I), "passport retention"),
    (re.compile(r"(recruitment|placement|processing|registration|training|visa)\s+fee\s+(?:of|is|required|must)|(?:pay|transfer)\s+(?:a\s+)?(?:deposit|fee)\s+(?:before|to\s+(?:secure|confirm|start))|biaya\s+(?:pendaftaran|penempatan|administrasi)", re.I), "recruitment or upfront fee"),
    (re.compile(r"(scam\s+compound|pig[- ]butchering|romance\s+scam|forced\s+labou?r|debt\s+bondage|cannot\s+leave\s+the\s+(?:compound|premises))", re.I), "trafficking / forced-labour indicators"),
    (re.compile(r"(online\s+(?:casino|gambling|betting)\s+(?:operator|agent|customer|marketing)|chat\s+(?:with|to)\s+(?:clients|customers|users)\s+to\s+(?:invest|deposit)|convince\s+(?:clients|people)\s+to\s+invest)", re.I), "fraud / illegal gambling duties"),
]
SAFETY_REVIEW = [
    (re.compile(r"(?:\bwa\.me/|\bt\.me/|telegram|whatsapp|\bline\s*id\b|wechat|\bsignal\b).{0,60}(?:apply|cv|resume|contact|send|hubungi)|(?:apply|send\s+(?:your\s+)?cv|contact|hubungi).{0,60}(?:\bwa\.me/|\bt\.me/|telegram|whatsapp|wechat)", re.I), "recruiting via personal chat accounts"),
    (re.compile(r"\b(urgent(?:ly)?\s+hiring|immediate(?:ly)?\s+start|start\s+tomorrow|limited\s+slots?|apply\s+today\s+only|segera\s+bergabung)\b", re.I), "urgency pressure"),
    (re.compile(r"\b(free\s+visa|visa\s+(?:guaranteed|will\s+be\s+arranged)|free\s+(?:flight|ticket|accommodation)\s+(?:and|&)\s+visa|guaranteed\s+(?:visa|work\s+permit))\b", re.I), "vague visa promises"),
    (re.compile(r"\b(send|submit|upload)\s+(?:a\s+)?(?:copy\s+of\s+)?(?:your\s+)?(passport|ktp|national\s+id|id\s+card|bank\s+(?:account|details|statement))\b", re.I), "upfront personal documents requested"),
    (re.compile(r"(?:promot\w*|sell\w*|market\w*)\W+(?:\w+\W+){0,4}(?:crypto\w*|usdt|forex)|\b(?:usdt|mass\s+messag\w*|bulk\s+messag\w*|typing\s+job|like\s+and\s+subscribe)\b", re.I), "crypto promotion / mass messaging"),
    (re.compile(r"\b(no\s+(?:written\s+)?contract|without\s+(?:a\s+)?contract|verbal\s+agreement)\b", re.I), "no written contract"),
]
UNVERIFIABLE_EMPLOYER = re.compile(r"^\s*(confidential|anonymous|undisclosed|private\s+company|our\s+client|perusahaan\s+rahasia)?\s*$", re.I)
TRUSTED_SOURCES = {"ats-search", "mycareersfuture-search", "nav-search", "platsbanken-search"}


def load_watchlist(path: Path | None = None) -> list[dict]:
    path = path or DATA / "safety_watchlist.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [w for w in data.get("entries", []) if isinstance(w, dict) and w.get("match") and w.get("source") and w.get("date")]


def safety_check(job: dict, salary: dict, watchlist: list[dict], today: date) -> dict:
    """Rule 4. Independent of fit. Records source+date for every finding."""
    override = job.get("safety_override")
    if isinstance(override, dict) and override.get("status") in SAFETY_STATUSES and override.get("source") and override.get("date"):
        return {"status": override["status"], "findings": [{"finding": override.get("note", "manual review"), "source": override["source"], "date": override["date"]}], "enhanced": False}
    text = text_of(job, "title", "company", "description", "location", "apply_url", "url")
    findings: list[dict] = []
    status = None
    hay = " ".join(str(job.get(k) or "") for k in ("company", "url", "apply_url")).lower()
    for w in watchlist:
        if str(w["match"]).lower() in hay:
            findings.append({"finding": f"official warning: {w.get('note', w['match'])}", "source": w["source"], "date": w["date"]})
            status = "rejected_safety_risk"
    for rx, label in SAFETY_REJECT:
        if rx.search(text):
            findings.append({"finding": label, "source": "posting text", "date": today.isoformat()})
            status = "rejected_safety_risk"
    review = [label for rx, label in SAFETY_REVIEW if rx.search(text)]
    idr = salary.get("salary_idr_monthly_min")
    vague = len(str(job.get("description") or "")) < 400
    if idr and idr > 120_000_000 and vague:
        review.append("very high pay for vague requirements")
    code = country_code(job)
    loc = text_of(job, "location", "description")
    enhanced = code in ENHANCED_COUNTRIES or bool(THAI_BORDER.search(loc)) or bool(HOTSPOTS.search(loc))
    if HOTSPOTS.search(text_of(job, "location")) or (code in ENHANCED_COUNTRIES and HOTSPOTS.search(loc)):
        review.append("worksite in a documented scam-compound area (enhanced screening)")
    company = str(job.get("company") or "")
    unverifiable = UNVERIFIABLE_EMPLOYER.match(company) is not None
    if unverifiable:
        review.append("employer not named")
    for label in review:
        findings.append({"finding": label, "source": "posting text", "date": today.isoformat()})
    if status is None:
        # Urgency and an unnamed employer are common in legitimate ads: alone
        # they only ask for verification; with any other signal they escalate.
        weak = {"urgency pressure", "employer not named"}
        strong = [r for r in review if r not in weak]
        if strong or len(review) >= 2 or (enhanced and review):
            status = "high_risk_manual_review"
        elif enhanced:
            status = "verification_pending"
        elif job.get("verification_status") == "unverified_lead" or job.get("source_type") == "social_post":
            status = "unknown"
        elif review:
            status = "verification_pending"
        elif job.get("portal") in TRUSTED_SOURCES and job.get("verification_status") != "unverified_lead":
            status = "verified_low_concern"
        else:
            status = "verification_pending"
    return {"status": status, "findings": findings, "enhanced": enhanced}


# ---------------------------------------------------------------- apply method

ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com", "smartrecruiters.com",
             "jobvite.com", "bamboohr.com", "teamtailor.com", "personio.de", "personio.com", "breezy.hr", "jazzhr.com",
             "pinpointhq.com", "homerun.co", "join.com", "comeet.com", "rippling-ats.com")
LOGIN_HOSTS = ("linkedin.com", "jobstreet.com", "jobsdb.com", "seek.com.au", "seek.co.nz", "glints.com", "kalibrr.com",
               "dealls.com", "kitalulus.com", "karir.com", "hiredly.com", "indeed.com", "wellfound.com", "stepstone.de",
               "reed.co.uk", "cwjobs.co.uk", "irishjobs.ie", "wanted.co.kr", "saramin.co.kr", "jumpit.co.kr", "finn.no",
               "welcometothejungle.com", "dice.com", "techinasia.com", "jobthai.com", "itviec.com", "topdev.vn",
               "vietnamworks.com", "trademe.co.nz", "myworkdayjobs.com", "workday.com", "karriere.at", "jobs.ch",
               "gaijinpot.com", "alfred.is", "djinni.co", "careers-page.com", "powertofly.com")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_APPLY = re.compile(r"(send|email|e-mail|submit|kirim)\w*\s+(?:your\s+|us\s+your\s+)?(?:cv|resume|application|lamaran|portfolio)|apply\s+(?:via|by)\s+e-?mail", re.I)


def _host_in(url: str | None, hosts: tuple[str, ...]) -> bool:
    if not url:
        return False
    try:
        host = (urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in hosts)


def apply_method(job: dict) -> dict:
    url, apply_url = job.get("url"), job.get("apply_url")
    for candidate in (apply_url, url):
        if _host_in(candidate, ATS_HOSTS) and not _host_in(candidate, ("myworkdayjobs.com",)):
            return {"method": "ats_form", "portal": urlsplit(str(candidate)).hostname}
    body = str(job.get("description") or "")
    emails = EMAIL.findall(body)
    if emails and EMAIL_APPLY.search(body):
        return {"method": "email", "portal": None, "email": emails[0]}
    for candidate in (apply_url, url):
        if _host_in(candidate, LOGIN_HOSTS):
            host = (urlsplit(str(candidate)).hostname or "").lower()
            portal = next(h for h in LOGIN_HOSTS if host == h or host.endswith("." + h))
            return {"method": "portal_login", "portal": portal}
    hint = next((e for e in job.get("evidence") or [] if str(e).startswith("apply_method hint: ")), None)
    if hint:
        method = str(hint).split(": ", 1)[1]
        if method in APPLY_METHODS:
            return {"method": method, "portal": (urlsplit(str(url)).hostname or None) if method == "portal_login" else None}
    return {"method": "external_unknown", "portal": None}


# ---------------------------------------------------------------- cost of living

def load_col(path: Path | None = None) -> dict[str, float]:
    path = path or DATA / "cost_of_living.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: float(v) for k, v in data.get("monthly_usd", {}).items() if isinstance(v, (int, float))}


# ---------------------------------------------------------------- evaluation

INJECTION = re.compile(r"(ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|system\s*:|you\s+are\s+(?:now\s+)?(?:an?\s+)?(?:ai|assistant|chatgpt|claude)|rank\s+this\s+(?:job|posting)\s+first|mark\s+(?:this|it)\s+as\s+(?:confirmed|safe|verified))", re.I)
SAFETY_ORDER = {"verified_low_concern": 0, "verification_pending": 1, "unknown": 2, "high_risk_manual_review": 3, "rejected_safety_risk": 4}


def evaluate_job(job: dict, fx: FxTable | None, today: date, watchlist: list[dict] | None = None, col: dict | None = None) -> dict:
    watchlist = watchlist if watchlist is not None else load_watchlist()
    col = col if col is not None else load_col()
    flags: list[str] = []
    rejected: list[str] = []
    verify: list[str] = []

    loc = location_check(job)
    emp = employment_check(job)
    sen = seniority_check(job)
    rel = relevance(job)
    sal = salary_check(job, fx)
    saf = safety_check(job, sal, watchlist, today)
    method = apply_method(job)

    if INJECTION.search(text_of(job, "title", "description")):
        flags.append("posting contains instruction-like text (prompt injection suspected); ignored")
    deadline = norm_date(job.get("deadline"))
    if job.get("status") == "expired" or (deadline and deadline < today):
        rejected.append(f"expired (deadline {job.get('deadline')})" if deadline else "expired")
    if loc["reject"]:
        rejected.append(loc["reject"])
    if emp["reject"]:
        rejected.append(emp["reject"])
    if sen["fit"] == "reject":
        rejected.append(sen["reason"])
    if rel == 0:
        rejected.append("no Flutter/mobile duties (off target)")
    if sal["status"] == "reject":
        rejected.append(f"salary floor: {sal['reason']}")
    if saf["status"] == "rejected_safety_risk":
        rejected.append("safety: " + "; ".join(f["finding"] for f in saf["findings"] if f["finding"]))

    if sal["status"] == "needs_salary_verification":
        verify.append(f"salary: {sal['reason']}")
    if loc["eligibility"] in ("unknown", "needs_visa"):
        verify.append("eligibility: " + ("remote eligibility for Indonesia-based applicants not stated" if loc["work_mode"] == "remote" else
                                          "work permit / visa sponsorship not stated" if loc["eligibility"] == "needs_visa" else
                                          "work arrangement and eligibility not stated"))
    if loc["visa"] == "portal_tag":
        flags.append("visa sponsorship tagged by the portal only - confirm in the employer's own text")
    if saf["status"] in ("verification_pending", "unknown"):
        verify.append("employer: " + ("unverified lead - find the real listing first" if saf["status"] == "unknown" else "employer/worksite not yet verified"))
    if emp["type"] in ("unknown", "part_time"):
        flags.append(f"employment type {emp['type'].replace('_', ' ')}")
    if sen["fit"] == "stretch":
        flags.append(sen["reason"])
    if sal.get("fx_stale"):
        flags.append(f"exchange rate from stale cache ({sal['fx_date']})")
    if saf["enhanced"]:
        flags.append("enhanced safety screening region")

    if rejected:
        section = "rejected"
    elif saf["status"] == "high_risk_manual_review":
        section = "manual_safety_review"
    elif verify:
        section = "needs_verification"
    else:
        section = "confirmed" if saf["status"] == "verified_low_concern" else "needs_verification"

    # Pay vs cost of living (ranking only; the floor is a minimum).
    col_ratio = None
    code = loc["country"]
    usd_rate = fx.idr_per_unit("USD") if fx else None
    if sal.get("salary_idr_monthly_min") and usd_rate and loc["work_mode"] != "remote":
        living = col.get(code or "")
        if living:
            col_ratio = round(sal["salary_idr_monthly_min"] / usd_rate / living, 2)
    elif sal.get("salary_idr_monthly_min") and usd_rate and col.get("ID"):
        col_ratio = round(sal["salary_idr_monthly_min"] / usd_rate / col["ID"], 2)  # remote: living in Indonesia

    posted = norm_date(job.get("date") or job.get("posted_date"))
    age = (today - posted).days if posted else 999
    rank_key = [
        SAFETY_ORDER.get(saf["status"], 2),  # unverified never outranks verified, whatever the pay
        -rel,
        -{"junior": 2, "unspecified": 1, "stretch": 0}.get(sen["fit"], 0),
        -{"full_time": 2, "contract": 1}.get(emp["type"], 0),
        -{"eligible_citizen": 3, "eligible_explicit": 3, "visa_evidence": 2, "unknown": 1}.get(loc["eligibility"], 0),
        -(1 if loc["work_mode"] == "remote" and loc["remote_eligibility"] == "eligible_explicit" else 0),
        -(1 if loc["visa"] == "positive" else 0),
        -(min(col_ratio, 5) if col_ratio else 0),
        -(1 if (code or "") in PRIORITY_COUNTRIES else 0),
        age,
        -len(job.get("evidence") or []),
    ]
    return {
        "section": section,
        "reasons": rejected if section == "rejected" else verify,
        "flags": flags,
        "salary": sal,
        "safety_screening": saf["status"],
        "safety_findings": saf["findings"],
        "apply_method": method["method"],
        "apply_portal": method.get("portal"),
        "apply_email": method.get("email"),
        "location": loc,
        "employment": emp["type"],
        "seniority": sen,
        "relevance": rel,
        "pay_vs_cost_of_living": col_ratio,
        "rank_key": rank_key,
    }


def evaluate(jobs: list[dict], fx: FxTable | None, today: date) -> dict:
    watchlist, col = load_watchlist(), load_col()
    sections: dict[str, list] = {s: [] for s in SECTIONS}
    needs_login: dict[str, list] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        r = evaluate_job(job, fx, today, watchlist, col)
        row = {"type": "job", **{k: job.get(k) for k in ("key", "id", "title", "company", "location", "url", "portal") if k in job}}
        row["rules"] = r
        sections[r["section"]].append(row)
        if r["apply_method"] == "portal_login" and r["section"] != "rejected":
            needs_login.setdefault(r["apply_portal"] or "unknown", []).append({"title": job.get("title"), "company": job.get("company"), "url": job.get("url")})
    for rows in sections.values():
        rows.sort(key=lambda row: row["rules"]["rank_key"])
    return {
        "sections": sections,
        "needs_login": needs_login,
        "counts": {s: len(v) for s, v in sections.items()},
        "fx": {"fetched_on": fx.fetched_on, "stale": fx.stale, "source": fx.source} if fx else None,
    }


def mark_safety(args) -> int:
    """Record a manual safety verdict on one seen_jobs entry, with source and date.

    The only way an entry from a non-trusted source becomes verified_low_concern:
    a person checked the employer and worksite and says where the evidence is.
    """
    if not (args.key and args.status and args.source):
        print(json.dumps({"error": "mark-safety needs --key, --status and --source", "code": "BAD_INPUT"}), file=sys.stderr)
        return 1
    try:
        doc = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"cannot read {args.state}: {exc}", "code": "BAD_INPUT"}), file=sys.stderr)
        return 1
    entry = doc.get("seen", {}).get(args.key)
    if not isinstance(entry, dict):
        print(json.dumps({"error": f"no entry {args.key}", "code": "NOT_FOUND"}), file=sys.stderr)
        return 1
    today = args.today or date.today().isoformat()
    entry["safety_override"] = {"status": args.status, "source": args.source[:300], "date": today,
                                "note": " ".join(args.note.split())[:200]}
    tmp = args.state.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.state)
    print(json.dumps({"key": args.key, "safety_override": entry["safety_override"]}, ensure_ascii=False))
    return 0


STORED_FIELDS = ("rules_section", "rules_reasons", "rules_flags", "safety_screening", "safety_findings", "apply_method", "apply_email",
                 "salary_idr_monthly_min", "fx_rate", "fx_date", "salary_check")


def stored_fields(rules: dict) -> dict:
    """The rule verdict as additive seen_jobs.json fields."""
    sal = rules.get("salary") or {}
    return {
        "rules_section": rules.get("section"),
        "rules_reasons": [str(r)[:200] for r in rules.get("reasons") or []][:6],
        "rules_flags": [str(f)[:200] for f in rules.get("flags") or []][:6],
        "safety_screening": rules.get("safety_screening"),
        "safety_findings": (rules.get("safety_findings") or [])[:6],
        "apply_method": rules.get("apply_method"),
        "apply_email": rules.get("apply_email"),
        "salary_idr_monthly_min": sal.get("salary_idr_monthly_min"),
        "fx_rate": sal.get("fx_rate"),
        "fx_date": sal.get("fx_date"),
        "salary_check": {"status": sal.get("status"), "reason": sal.get("reason"), "original": sal.get("original")},
    }


def store(args) -> int:
    """Write evaluate's verdicts onto seen_jobs.json entries (additive fields only)."""
    try:
        results = json.loads(args.results.read_text(encoding="utf-8"))
        doc = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, AttributeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"store needs --results and a readable --state: {exc}", "code": "BAD_INPUT"}), file=sys.stderr)
        return 1
    seen = doc.get("seen", {})
    written, missing = [], []
    for item in results if isinstance(results, list) else []:
        key, rules = item.get("key"), item.get("rules")
        if not isinstance(rules, dict) or rules.get("section") not in SECTIONS or key not in seen:
            missing.append(key)
            continue
        seen[key].update(stored_fields(rules))
        written.append(key)
    tmp = args.state.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.state)
    print(json.dumps({"written": written, "skipped": missing}))
    return 0 if not missing else 1


def read_jobs(path: Path) -> list[dict]:
    return read_jobs_text(path.read_text(encoding="utf-8"))


def read_jobs_text(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("results") if "results" in data else list(data.get("seen", {}).values()) if "seen" in data else [data]
    if not isinstance(data, list):
        raise ValueError("input must be a JSON array of jobs")
    return data


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Deterministic hard rules for scraped jobs")
    parser.add_argument("command", choices=["evaluate", "mark-safety", "store"])
    parser.add_argument("--in", dest="inp", help="jobs JSON file, or - for stdin")
    parser.add_argument("--results", type=Path, help="store: [{key, rules}] from evaluate")
    parser.add_argument("--fx-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true", help="never fetch exchange rates; cache only")
    parser.add_argument("--today", help="YYYY-MM-DD (tests)")
    parser.add_argument("--state", type=Path, default=ROOT / "job_scraper" / "seen_jobs.json")
    parser.add_argument("--key", help="mark-safety: seen_jobs.json key")
    parser.add_argument("--status", choices=SAFETY_STATUSES, help="mark-safety: the reviewed status")
    parser.add_argument("--source", help="mark-safety: where the evidence is (URL or document)")
    parser.add_argument("--note", default="", help="mark-safety: one line, plain text")
    args = parser.parse_args(argv)
    if args.command == "mark-safety":
        return mark_safety(args)
    if args.command == "store":
        return store(args)
    if not args.inp:
        parser.error("evaluate needs --in")
    try:
        jobs = read_jobs_text(sys.stdin.read()) if args.inp == "-" else read_jobs(Path(args.inp))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "code": "BAD_INPUT"}), file=sys.stderr)
        return 1
    today = date.fromisoformat(args.today) if args.today else date.today()
    fx = load_rates(args.fx_cache, today, offline=args.offline)
    print(json.dumps(evaluate(jobs, fx, today), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
