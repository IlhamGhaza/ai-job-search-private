#!/usr/bin/env python3
"""The deterministic half of /propose: preconditions, claim checks on a
drafted proposal (before and after the humanizer), form filling that stops
before Send, the duplicate-proposal guard, and freelance_tracker.csv.

Run from the repo root (see .claude/commands/propose.md for the full flow):

    python tools/freelance_guard.py humanizer-status
    python tools/freelance_guard.py check --gig-file gig.json [--safety-reviewed yes]
    python tools/freelance_guard.py claims-check --draft draft.txt --gig-file gig.json [--allow "IDR 150,000/hour"]
    python tools/freelance_guard.py humanizer-check --draft draft.txt --humanized humanized.txt --gig-file gig.json [--allow ...]
    python tools/freelance_guard.py login --platform upwork.com
    python tools/freelance_guard.py fill --plan plan.json [--session S]
    python tools/freelance_guard.py send --plan plan.json --review-hash H --confirm yes --mode confirm_then_click --approve-spend N
    python tools/freelance_guard.py record --gig-file gig.json --rate R --connects-spent N [--screenshot P] --user-confirmed yes
    python tools/freelance_guard.py email-draft --gig-file gig.json --to ADDR --subject S --body-file B --out draft.eml

Hard guarantees, enforced here rather than left to the model:
- One proposal per gig (freelance_tracker.csv), at most 5 per platform per day.
- Rejected gigs are refused; a manual-safety-review gig needs --safety-reviewed yes.
- Upwork and Freelancer.com are fill-only: `send` refuses them outright, so
  this tool never spends Connects or bids there. Elsewhere the default is
  fill-only too; `send` clicks only with --confirm yes, the review hash of the
  exact plan the user saw, and --approve-spend equal to the plan's cost.
- `fill` never clicks the send control; a login/2FA/CAPTCHA page stops it.
- The proposal text filled is byte-for-byte the approved proposal file.
- Claims: every number, tech term and reputation claim in a draft must be in
  the profile, the gig text or a value the user gave (--allow); the
  humanizer's output may not add any that the draft did not have.
- Payment, passport/ID or bank fields stop the run (submit_guard.FORBIDDEN_FIELD).

Reuses tools/submit_guard.py (browser runner, persistent profile, login,
forbidden-field rule, profile text) and tools/gig_rules.py. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_rates import DEFAULT_CACHE, load_rates  # noqa: E402
from gig_rules import evaluate_gig, gig_keys, proposed_keys  # noqa: E402
from submit_guard import (  # noqa: E402
    FORBIDDEN_FIELD,
    LOGIN_WALL,
    SCREENSHOTS,
    Refused,
    Runner,
    host_of,
    load_json,
    login,
    open_browser,
    playwright_runner,
    profile_text,
    slug,
)

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "freelance_tracker.csv"
TRACKER_FIELDS = ["gig", "platform", "gig_id", "url", "date", "rate", "status", "connects_spent", "screenshot"]
SHOTS = SCREENSHOTS / "freelance"
PLUGINS_FILE = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
DAILY_LIMIT_PER_PLATFORM = 5
# Their terms forbid automated proposals/bids: the user always clicks Send.
ALWAYS_FILL_ONLY = re.compile(r"(^|\.)(upwork\.com|freelancer\.[a-z.]+)$")

TECH_TERMS = [
    "flutter", "dart", "firebase", "bloc", "getx", "provider", "riverpod", "mobx", "redux", "clean architecture",
    "swift", "swiftui", "kotlin", "jetpack compose", "java", "objective-c", "react native", "react", "vue", "angular",
    "node.js", "nodejs", "express", "nestjs", "laravel", "php", "python", "django", "flask", "go", "golang", "rust",
    "typescript", "javascript", "sql", "sqlite", "mysql", "postgresql", "mongodb", "redis", "supabase", "appwrite",
    "graphql", "rest api", "dio", "jwt", "mqtt", "websocket", "grpc", "aws", "gcp", "azure", "docker", "kubernetes",
    "codemagic", "fastlane", "github actions", "tensorflow lite", "tensorflow", "gemini", "openai", "stripe", "midtrans",
    "revenuecat", "onesignal", "sentry", "hive", "isar", "drift", "google maps", "figma", "unity", "xamarin", "ionic",
    "kmm", "kotlin multiplatform", "in-app purchase", "app store connect", "play console", "bluetooth", "ble", "nfc", "arcore", "arkit",
]
REPUTATION = re.compile(
    r"\b(top[- ]rated(?:\s+plus)?|rising\s+talent|expert[- ]vetted|5[- ]star|five[- ]star|\d+(?:\.\d+)?\s*%\s*job\s+success|"
    r"job\s+success\s+score|\d+\+?\s*(?:happy\s+)?(?:reviews|clients|customers)|(?:many|dozens\s+of|hundreds\s+of)\s+(?:happy\s+)?clients)\b",
    re.I,
)
NUMBER = re.compile(r"(?<![\w.])\d[\d.,]*\+?")


# ---------------------------------------------------------------- humanizer

def humanizer_installed(plugins_file: Path = PLUGINS_FILE) -> bool:
    """True when Claude Code lists a humanizer@<marketplace> plugin as installed."""
    data = load_json(plugins_file, {})
    plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
    return any(str(k).split("@")[0] == "humanizer" and v for k, v in plugins.items())


# ---------------------------------------------------------------- claims

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").lower()


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[.,+]+$", "", n).replace(",", "") for n in NUMBER.findall(text or "")} - {""}


def _terms(text: str) -> set[str]:
    t = _norm(text)
    return {term for term in TECH_TERMS if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", t)}


def claims_check(draft: str, gig_text: str, allow: list[str], profile: str | None = None) -> list[str]:
    """Problems with what a proposal claims. Empty list = nothing unsupported."""
    profile = profile if profile is not None else profile_text()
    known = "\n".join([profile, gig_text, *allow])
    problems = []
    for n in sorted(_numbers(draft) - _numbers(known)):
        problems.append(f"number '{n}' is not in your profile, the gig or a value you gave - ASK USER or remove it")
    prof_terms = _terms(profile)
    for term in sorted(_terms(draft) - prof_terms - _terms("\n".join(allow))):
        where = "the gig asks for it" if term in _terms(gig_text) else "not in the gig either"
        problems.append(f"'{term}' is not in your profile ({where}) - mention it only as something you have not used yet, or ASK USER")
    for m in REPUTATION.finditer(draft):
        if _norm(m.group(0)) not in _norm(known):
            problems.append(f"reputation claim '{m.group(0)}' is not in your profile - never invent reviews, ratings or badges")
    return problems


def humanizer_check(draft: str, humanized: str, gig_text: str, allow: list[str], profile: str | None = None) -> list[str]:
    """What the humanizer added that the approved draft did not say, plus the plain claims check."""
    problems = []
    for n in sorted(_numbers(humanized) - _numbers(draft)):
        problems.append(f"humanizer added the number '{n}'")
    for term in sorted(_terms(humanized) - _terms(draft)):
        problems.append(f"humanizer added the claim '{term}'")
    for m in REPUTATION.finditer(humanized):
        if _norm(m.group(0)) not in _norm(draft):
            problems.append(f"humanizer added the reputation claim '{m.group(0)}'")
    problems += [p for p in claims_check(humanized, gig_text, allow, profile) if p not in problems]
    return problems


# ---------------------------------------------------------------- tracker

def read_tracker(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append_tracker(path: Path, row: dict) -> None:
    new = not path.is_file()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=TRACKER_FIELDS, lineterminator="\n")
    if new:
        writer.writeheader()
    writer.writerow({k: str(row.get(k, "")).replace("\n", " ") for k in TRACKER_FIELDS})
    with path.open("a", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())


def platform_key(gig: dict) -> str:
    return str(gig.get("platform") or host_of(gig.get("url"))).strip().lower()


def proposals_today(path: Path, platform: str, today: date) -> int:
    return sum(1 for r in read_tracker(path) if r.get("platform", "").strip().lower() == platform and r.get("date") == today.isoformat()
               and r.get("status") in ("proposed", "sent"))


def already_proposed(path: Path, gig: dict) -> bool:
    return any(k in proposed_keys(path) for k in gig_keys(gig))


def fill_only_forced(url: str | None) -> bool:
    return bool(ALWAYS_FILL_ONLY.search(host_of(url)))


# ---------------------------------------------------------------- check

def check(gig: dict, *, safety_reviewed: bool = False, tracker: Path = TRACKER, today: date | None = None, fx=None) -> dict:
    today = today or date.today()
    reasons, warnings = [], []
    for field in ("platform", "gig_id", "url", "title"):
        if not gig.get(field):
            reasons.append(f"gig.{field} missing")
    fx = fx if fx is not None else load_rates(DEFAULT_CACHE, today, offline=True)
    rules = evaluate_gig(gig, fx, today)
    if rules["section"] == "rejected":
        reasons.append("gig rejected by the rules: " + "; ".join(rules["reasons"]))
    elif rules["section"] == "manual_safety_review" and not safety_reviewed:
        reasons.append("gig needs manual safety review first (" + "; ".join(rules["reasons"]) + "); rerun with --safety-reviewed yes once the user has checked it")
    elif rules["section"] == "needs_budget_client_review":
        warnings += rules["reasons"]
    if already_proposed(tracker, gig):
        reasons.append("already proposed to this gig - never propose twice")
    platform = platform_key(gig)
    if proposals_today(tracker, platform, today) >= DAILY_LIMIT_PER_PLATFORM:
        reasons.append(f"{DAILY_LIMIT_PER_PLATFORM} proposals on {platform} today already - the daily limit")
    method = gig.get("apply_method") or "platform_proposal"
    forced = fill_only_forced(gig.get("url"))
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "section": rules["section"],
        "rate": rules["rate"],
        "apply_method": method,
        "mode_default": "email_draft" if method == "email" else "fill_only",
        "fill_only_forced": forced,
        "connects_or_bids_cost": gig.get("connects_or_bids_cost"),
    }


# ---------------------------------------------------------------- browser

def validate_plan(plan: dict) -> list[str]:
    problems = []
    gig = plan.get("gig") or {}
    if not gig.get("url"):
        problems.append("plan.gig.url missing")
    proposal_file = plan.get("proposal_file")
    proposal = Path(proposal_file).read_text(encoding="utf-8").strip() if proposal_file and Path(proposal_file).is_file() else None
    if proposal is None:
        problems.append("plan.proposal_file missing: the approved proposal text must be saved to a file first")
    if not plan.get("send_ref"):
        problems.append("plan.send_ref missing (the Send / Submit proposal control, recorded but never clicked by fill)")
    for i, f in enumerate(plan.get("fields", [])):
        label = str(f.get("label") or f"field {i}")
        value = f.get("value")
        if FORBIDDEN_FIELD.search(label) or FORBIDDEN_FIELD.search(str(value or "")):
            problems.append(f"STOP - possible scam: the form asks for '{label}' (payment / passport / ID / bank details are never entered)")
            continue
        if not f.get("ref"):
            problems.append(f"'{label}': no element ref from the page snapshot")
        if f.get("ref") and f.get("ref") == plan.get("send_ref"):
            problems.append(f"'{label}' targets the send control")
        source = f.get("source")
        if source == "proposal":
            if proposal is not None and str(value or "").strip() != proposal:
                problems.append(f"'{label}': text differs from the approved proposal file")
        elif source == "rate":
            if str(value) != str(plan.get("rate")):
                problems.append(f"'{label}': value differs from plan.rate the user approved")
        elif not f.get("user_confirmed"):
            problems.append(f"ASK USER - '{label}': not the proposal or the rate; set user_confirmed only after the user gave this value")
        if value in (None, "") and f.get("kind", "fill") != "check":
            problems.append(f"ASK USER - '{label}': no value")
    return problems


def review_hash(plan: dict) -> str:
    material = json.dumps({"url": plan.get("gig", {}).get("url"), "rate": plan.get("rate"), "cost": plan.get("connects_or_bids_cost"),
                           "fields": [(f.get("label"), f.get("ref"), f.get("value")) for f in plan.get("fields", [])],
                           "send_ref": plan.get("send_ref")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _guard_repeat(plan: dict, tracker: Path, today: date) -> None:
    gig = plan.get("gig") or {}
    if already_proposed(tracker, gig):
        raise Refused("already proposed to this gig - never propose twice")
    if proposals_today(tracker, platform_key(gig), today) >= DAILY_LIMIT_PER_PLATFORM:
        raise Refused(f"daily limit of {DAILY_LIMIT_PER_PLATFORM} proposals on this platform reached")


def fill(plan: dict, runner: Runner, *, tracker: Path = TRACKER, shots: Path = SHOTS, today: date | None = None) -> dict:
    """Fill the proposal form, screenshot, STOP. Never clicks plan['send_ref']."""
    problems = validate_plan(plan)
    if problems:
        raise Refused("plan refused:\n- " + "\n- ".join(problems))
    _guard_repeat(plan, tracker, today or date.today())
    if LOGIN_WALL.search(runner(["snapshot"])):
        raise Refused("PAUSE - a login, 2FA or CAPTCHA page is showing. Handle it yourself in the browser window, then run fill again.")
    for f in plan["fields"]:
        kind = f.get("kind", "fill")
        if kind == "select":
            runner(["select", f["ref"], str(f["value"])])
        elif kind == "check":
            runner(["check", f["ref"]])
        else:
            runner(["fill", f["ref"], str(f["value"])])
    shots.mkdir(parents=True, exist_ok=True)
    gig = plan["gig"]
    shot = shots / f"{slug(gig.get('platform', ''))}_{slug(str(gig.get('gig_id', '')))}_review.png"
    runner(["screenshot", f"--filename={shot}"])
    forced = fill_only_forced(gig.get("url"))
    return {
        "status": "filled_waiting_for_user",
        "review_hash": review_hash(plan),
        "screenshot": str(shot),
        "rate": plan.get("rate"),
        "connects_or_bids_cost": plan.get("connects_or_bids_cost"),
        "fields": [{"label": f.get("label"), "value": f.get("value")} for f in plan["fields"]],
        "fill_only_forced": forced,
        "next": ("Show the user the screenshot, the exact text, the rate and the Connects/bids it will spend. "
                 + ("This platform is fill-only: the user clicks Send, then run record --user-confirmed yes."
                    if forced else "Run send only after an explicit 'yes' and --approve-spend equal to the cost.")),
    }


def send(plan: dict, runner: Runner, *, confirm: str, given_hash: str, mode: str, approve_spend: str | None,
         tracker: Path = TRACKER, shots: Path = SHOTS, today: date | None = None) -> dict:
    gig = plan.get("gig") or {}
    if fill_only_forced(gig.get("url")):
        raise Refused("Upwork and Freelancer.com are fill-only: their terms forbid automated proposals. The user clicks Send, then run record --user-confirmed yes.")
    if mode != "confirm_then_click":
        raise Refused("fill-only mode: the user clicks Send themselves, then run record --user-confirmed yes")
    if confirm != "yes":
        raise Refused("not sent: the user has not said an explicit 'yes'")
    if given_hash != review_hash(plan):
        raise Refused("not sent: the plan changed after the user reviewed it; run fill again and re-confirm")
    cost = plan.get("connects_or_bids_cost")
    if cost not in (None, 0, "0") and str(approve_spend) != str(cost):
        raise Refused(f"not sent: this proposal spends {cost} credits/bids; pass --approve-spend {cost} only after the user approved that spend")
    if cost is None and approve_spend is None:
        raise Refused("not sent: the cost to apply is unknown; read it on the page, put it in plan.connects_or_bids_cost and get the user's approval")
    today = today or date.today()
    _guard_repeat(plan, tracker, today)
    runner(["click", plan["send_ref"]])
    shots.mkdir(parents=True, exist_ok=True)
    shot = shots / f"{slug(gig.get('platform', ''))}_{slug(str(gig.get('gig_id', '')))}_sent.png"
    runner(["screenshot", f"--filename={shot}"])
    return record(gig, plan.get("rate"), cost or 0, str(shot), tracker=tracker, today=today)


def record(gig: dict, rate, connects_spent, screenshot: str | None, *, tracker: Path = TRACKER, today: date | None = None,
           status: str = "proposed") -> dict:
    today = today or date.today()
    if already_proposed(tracker, gig):
        raise Refused("already recorded as proposed")
    rel = None
    if screenshot:
        try:
            rel = str(Path(screenshot).resolve().relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel = Path(screenshot).name
    row = {"gig": gig.get("title", ""), "platform": gig.get("platform", ""), "gig_id": gig.get("gig_id", ""), "url": gig.get("url", ""),
           "date": today.isoformat(), "rate": rate if rate is not None else "", "status": status,
           "connects_spent": connects_spent if connects_spent is not None else "", "screenshot": rel or ""}
    append_tracker(tracker, row)
    return {**row, "status": "recorded", "tracker_status": status}


# ---------------------------------------------------------------- email

def email_draft(gig: dict, to: str, subject: str, body: str, out: Path, sender: str | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", to):
        raise Refused(f"'{to}' is not an email address")
    text = "\n".join(str(gig.get(k) or "") for k in ("title", "description"))
    if to.lower() not in text.lower():
        raise Refused(f"{to} does not appear in the gig text; only the gig's own contact address is used")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["X-Unsent"] = "1"  # opens as a draft in mail clients
    msg.set_content(body.strip() + "\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(msg))
    return {"status": "draft_saved", "eml": str(out), "to": to, "subject": subject,
            "next": "Show the draft. Send only after an explicit 'yes', then run record --user-confirmed yes."}


# ---------------------------------------------------------------- CLI

def _read(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path else ""


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Guards for /propose")
    sub = p.add_subparsers(dest="cmd", required=True)
    hs = sub.add_parser("humanizer-status")
    hs.add_argument("--plugins-file", type=Path, default=PLUGINS_FILE)
    c = sub.add_parser("check")
    c.add_argument("--gig-file", type=Path, required=True)
    c.add_argument("--safety-reviewed", default="no")
    for name in ("claims-check", "humanizer-check"):
        s = sub.add_parser(name)
        s.add_argument("--draft", type=Path, required=True)
        s.add_argument("--gig-file", type=Path, required=True)
        s.add_argument("--allow", action="append", default=[], help="a value the user gave in this conversation (rate, availability, portfolio URL)")
        if name == "humanizer-check":
            s.add_argument("--humanized", type=Path, required=True)
    lg = sub.add_parser("login")
    lg.add_argument("--platform", required=True, help="host, e.g. upwork.com")
    lg.add_argument("--session", default="propose")
    o = sub.add_parser("open")
    o.add_argument("--url", required=True)
    o.add_argument("--session", default="propose")
    f = sub.add_parser("fill")
    f.add_argument("--plan", type=Path, required=True)
    f.add_argument("--session", default="propose")
    s = sub.add_parser("send")
    s.add_argument("--plan", type=Path, required=True)
    s.add_argument("--session", default="propose")
    s.add_argument("--review-hash", required=True)
    s.add_argument("--confirm", required=True)
    s.add_argument("--mode", choices=["fill_only", "confirm_then_click"], required=True)
    s.add_argument("--approve-spend")
    r = sub.add_parser("record")
    r.add_argument("--gig-file", type=Path, required=True)
    r.add_argument("--rate", required=True)
    r.add_argument("--connects-spent", required=True)
    r.add_argument("--screenshot")
    r.add_argument("--user-confirmed", required=True)
    e = sub.add_parser("email-draft")
    e.add_argument("--gig-file", type=Path, required=True)
    e.add_argument("--to", required=True)
    e.add_argument("--subject", required=True)
    e.add_argument("--body-file", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--from", dest="sender")
    args = p.parse_args(argv)

    def emit(obj) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    try:
        if args.cmd == "humanizer-status":
            installed = humanizer_installed(args.plugins_file)
            emit({"installed": installed, "next": "Run the draft through the humanizer skill, then humanizer-check." if installed else
                  "Humanizer plugin not installed: skip that step and tell the user once (/plugin install humanizer@humanizer)."})
            return 0
        if args.cmd in ("check", "claims-check", "humanizer-check", "record", "email-draft"):
            gig = load_json(args.gig_file, None)
            if not isinstance(gig, dict):
                raise Refused(f"{args.gig_file} is not a gig JSON object")
        if args.cmd == "check":
            result = check(gig, safety_reviewed=args.safety_reviewed == "yes")
            emit(result)
            return 0 if result["allowed"] else 3
        if args.cmd in ("claims-check", "humanizer-check"):
            gig_text = "\n".join(str(gig.get(k) or "") for k in ("title", "description")) + " " + " ".join(map(str, gig.get("skills") or []))
            if args.cmd == "claims-check":
                problems = claims_check(_read(args.draft), gig_text, args.allow)
            else:
                problems = humanizer_check(_read(args.draft), _read(args.humanized), gig_text, args.allow)
            emit({"ok": not problems, "problems": problems})
            return 0 if not problems else 3
        if args.cmd == "login":
            emit(login(playwright_runner(args.session), args.platform))
            return 0
        if args.cmd == "open":
            open_browser(playwright_runner(args.session), args.url)
            emit({"status": "opened", "next": "log in yourself if the platform asks; then snapshot"})
            return 0
        if args.cmd == "fill":
            emit(fill(load_json(args.plan, {}), playwright_runner(args.session)))
            return 0
        if args.cmd == "send":
            emit(send(load_json(args.plan, {}), playwright_runner(args.session), confirm=args.confirm, given_hash=args.review_hash,
                      mode=args.mode, approve_spend=args.approve_spend))
            return 0
        if args.cmd == "record":
            if args.user_confirmed != "yes":
                raise Refused("record needs --user-confirmed yes (the user confirmed the proposal was sent)")
            emit(record(gig, args.rate, args.connects_spent, args.screenshot))
            return 0
        if args.cmd == "email-draft":
            emit(email_draft(gig, args.to, args.subject, _read(args.body_file), args.out, args.sender))
            return 0
    except Refused as exc:
        print(json.dumps({"refused": str(exc), "code": "REFUSED"}, ensure_ascii=False), file=sys.stderr)
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
