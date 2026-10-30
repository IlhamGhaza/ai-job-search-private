#!/usr/bin/env python3
"""The deterministic half of /submit: preconditions, form filling that stops
before the final click, the duplicate guard, tracker recording, email drafts.

Run from the repo root (see .claude/commands/submit.md for the full flow):

    python tools/submit_guard.py login   --portal linkedin.com     # once per portal; you sign in yourself
    python tools/submit_guard.py check   --company C --role R (--key K | --job-file job.json)
    python tools/submit_guard.py fill    --plan plan.json [--session S]
    python tools/submit_guard.py submit  --plan plan.json --review-hash H --confirm yes [--session S]
    python tools/submit_guard.py record  --company C --role R --url U --channel CH [--screenshot P] --user-confirmed yes
    python tools/submit_guard.py email-draft --title T --to ADDR --posting-file F
                                  --body-file B --cv cv.pdf --cover cover.pdf --out draft.eml

Hard guarantees, enforced here rather than left to the model:
- No submission unless /apply produced both PDFs, the hard rules put the job in
  `confirmed`, and safety_screening is `verified_low_concern`.
- One submission per job (tracker status + ledger), max 10 per portal per day.
- `fill` never clicks the submit control; `submit` clicks it only with
  --confirm yes AND the review hash of the exact plan the user saw.
- Answers come from the profile only: every filled value must quote a line of
  CLAUDE.md or 01-candidate-profile.md, or be one of the two PDFs. Unknown
  answers stop the run so the user is asked.
- Payment, passport/ID or bank fields stop the run and flag a possible scam.
- No passwords, cookies or tokens are read, typed or stored. The browser
  profile lives in .browser-profile/ (gitignored); the user logs in by hand.

Browser actions go through the Playwright CLI (`playwright-cli`), headed, with
a persistent profile. Tests inject a fake runner; no live site is touched.
Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_rates import DEFAULT_CACHE, load_rates  # noqa: E402
from job_rules import apply_method, evaluate_job  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "job_search_tracker.csv"
SEEN = ROOT / "job_scraper" / "seen_jobs.json"
LEDGER = ROOT / "job_scraper" / "submissions.json"
PROFILE_FILES = [ROOT / "CLAUDE.md", ROOT / ".claude" / "skills" / "job-application-assistant" / "01-candidate-profile.md"]
SCREENSHOTS = ROOT / ".submit-screenshots"
BROWSER_PROFILE = ROOT / ".browser-profile"
DAILY_LIMIT_PER_PORTAL = 10
SUBMITTED = {"applied", "interview", "offer", "hired", "rejected", "no_response", "no response", "offer_declined", "offer declined", "withdrawn"}
# Portals whose terms restrict automation: default to fill-only (the user clicks submit).
FILL_ONLY_PORTALS = ("linkedin.com", "jobstreet.com", "jobsdb.com", "seek.com.au", "seek.co.nz", "glints.com", "indeed.com",
                     "kalibrr.com", "wellfound.com", "stepstone.de", "myworkdayjobs.com", "workday.com")
FORBIDDEN_FIELD = re.compile(
    r"(credit\s*card|card\s*number|cvv|cvc|expiry|payment|pay\s+now|deposit|bank\s*(account|details|transfer)|iban|"
    r"passport|national\s*id|\bktp\b|\bnik\b|id\s*card|ssn|social\s+security|tax\s*id|npwp|driver'?s?\s+licen[cs]e)",
    re.I,
)

# A page the user must handle themselves (login, 2FA, CAPTCHA); /propose reuses it.
LOGIN_WALL = re.compile(r"(captcha|verify\s+you\s+are\s+human|two-factor|2fa|one-time\s+code|sign\s+in|log\s*in\s+to\s+continue)", re.I)

Runner = Callable[[list[str]], str]


class Refused(Exception):
    """A guard said no. The message is shown to the user verbatim."""


# ---------------------------------------------------------------- small IO helpers

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", norm(text)).strip("_")[:60] or "job"


def host_of(url: str | None) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(str(url or "")).hostname or "").lower()


def portal_key(url: str | None) -> str:
    host = host_of(url)
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) > 2 and len(parts[-1]) == 2 and len(parts[-2]) <= 3 else ".".join(parts[-2:])


# ---------------------------------------------------------------- tracker

def read_tracker(path: Path) -> tuple[list[str], list[dict], str]:
    raw = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader.fieldnames or []), list(reader), newline


def find_rows(rows: list[dict], company: str, role: str) -> list[dict]:
    return [r for r in rows if norm(r.get("company")) == norm(company) and norm(r.get("role")) == norm(role)]


def update_tracker(path: Path, company: str, role: str, channel: str, note: str) -> None:
    """Set status=applied on the one matching row and append a dated note.

    Same rules as /outcome Step 4: touch only status/notes (and channel when
    empty), never restructure, never quote, never touch other rows.
    """
    header, rows, newline = read_tracker(path)
    matches = find_rows(rows, company, role)
    if len(matches) != 1:
        raise Refused(f"expected exactly one tracker row for {company} / {role}, found {len(matches)}")
    row = matches[0]
    clean = re.sub(r"[,\"\r\n]+", " ", note).strip()
    row["status"] = "applied"
    if "channel" in row and not (row.get("channel") or "").strip():
        row["channel"] = re.sub(r"[,\"\r\n]+", " ", channel)
    row["notes"] = (row.get("notes") or "").strip()
    row["notes"] = f"{row['notes']} | {clean}" if row["notes"] else clean
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=header, lineterminator=newline, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    tmp = path.with_suffix(".csv.tmp")
    tmp.write_text(out.getvalue(), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- ledger

def ledger_entries(path: Path) -> list[dict]:
    data = load_json(path, {"submissions": []})
    return data.get("submissions", []) if isinstance(data, dict) else []


def already_submitted(path: Path, company: str, role: str, url: str | None) -> dict | None:
    for e in ledger_entries(path):
        if (url and e.get("url") == url) or (norm(e.get("company")) == norm(company) and norm(e.get("role")) == norm(role)):
            return e
    return None


def submissions_today(path: Path, portal: str, today: date) -> int:
    return sum(1 for e in ledger_entries(path) if e.get("portal") == portal and str(e.get("submitted_at", "")).startswith(today.isoformat()))


def add_ledger(path: Path, entry: dict) -> None:
    data = load_json(path, {"submissions": []})
    if not isinstance(data, dict):
        data = {"submissions": []}
    data.setdefault("submissions", []).append(entry)
    save_json(path, data)


# ---------------------------------------------------------------- preconditions

def pdf_for(path_text: str | None) -> Path | None:
    if not path_text:
        return None
    p = (ROOT / path_text) if not Path(path_text).is_absolute() else Path(path_text)
    pdf = p.with_suffix(".pdf")
    return pdf if pdf.is_file() else None


def find_seen(seen_path: Path, key: str | None, url: str | None) -> dict | None:
    seen = load_json(seen_path, {}).get("seen", {})
    if key and key in seen:
        return seen[key]
    if url:
        for entry in seen.values():
            if isinstance(entry, dict) and str(entry.get("url", "")).rstrip("/") == url.rstrip("/"):
                return entry
    return None


def check(company: str, role: str, *, key: str | None = None, job: dict | None = None, tracker: Path = TRACKER,
          seen_path: Path = SEEN, ledger: Path = LEDGER, today: date | None = None, fx_cache: Path = DEFAULT_CACHE) -> dict:
    """Every precondition for /submit. Returns {allowed, reasons, ...}; never raises on a 'no'."""
    today = today or date.today()
    reasons: list[str] = []
    warnings: list[str] = []
    row = None
    if not tracker.is_file():
        reasons.append("no job_search_tracker.csv: run /apply first")
    else:
        _, rows, _ = read_tracker(tracker)
        matches = find_rows(rows, company, role)
        if not matches:
            reasons.append("no tracker row for this job: /apply has not finished for it")
        elif len(matches) > 1:
            reasons.append("several tracker rows match; resolve them with /outcome first")
        else:
            row = matches[0]
            if norm(row.get("status")) in SUBMITTED:
                reasons.append(f"already submitted (tracker status '{row.get('status')}') - never submit twice")
    cv_pdf = pdf_for(row.get("cv_file")) if row else None
    cover_pdf = pdf_for(row.get("cover_letter_file")) if row else None
    if row and (not cv_pdf or not cover_pdf):
        reasons.append("compiled CV and cover letter PDFs not found next to the tracker's cv_file/cover_letter_file")
    url = (row or {}).get("source") or (job or {}).get("url")
    entry = job if job is not None else find_seen(seen_path, key, url)
    if entry is None:
        reasons.append("no job record (seen_jobs key or --job-file) to run the hard rules on")
        verdict = None
    else:
        fx = load_rates(fx_cache, today, offline=True)
        verdict = evaluate_job(entry, fx, today)
        if verdict["section"] != "confirmed":
            reasons.append(f"hard rules put this job in '{verdict['section']}': " + "; ".join(verdict["reasons"]))
        if verdict["safety_screening"] != "verified_low_concern":
            reasons.append(f"safety_screening is '{verdict['safety_screening']}', not verified_low_concern")
        url = url or entry.get("url")
    prior = already_submitted(ledger, company, role, url)
    if prior:
        reasons.append(f"already submitted on {prior.get('submitted_at')} - never submit twice")
    method = apply_method(entry or {"url": url}) if (entry or url) else {"method": "external_unknown", "portal": None}
    portal = portal_key((entry or {}).get("apply_url") or url)
    if submissions_today(ledger, portal, today) >= DAILY_LIMIT_PER_PORTAL:
        reasons.append(f"daily limit reached: {DAILY_LIMIT_PER_PORTAL} submissions on {portal} today")
    fill_only = method["method"] == "portal_login" or any(portal.endswith(p) for p in FILL_ONLY_PORTALS)
    if fill_only:
        warnings.append(
            f"Automating {portal} may violate its Terms of Use and risk account restriction. Default mode: fill only - "
            "the tool fills the form and you click Submit yourself."
        )
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "apply_method": method["method"],
        "apply_email": method.get("email"),
        "portal": portal,
        "mode_default": "fill_only" if fill_only else "confirm_then_click",
        "url": url,
        "cv_pdf": str(cv_pdf) if cv_pdf else None,
        "cover_pdf": str(cover_pdf) if cover_pdf else None,
        "section": verdict["section"] if verdict else None,
        "safety_screening": verdict["safety_screening"] if verdict else None,
    }


# ---------------------------------------------------------------- answers & plans

def profile_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in PROFILE_FILES if p.is_file())


def validate_plan(plan: dict, profile: str | None = None) -> list[str]:
    """Problems that stop a fill. Empty list = plan may be filled."""
    profile_norm = norm(profile if profile is not None else profile_text())
    problems: list[str] = []
    allowed_uploads = {str(Path(p).resolve()) for p in (plan.get("cv_pdf"), plan.get("cover_pdf")) if p}
    if not plan.get("job", {}).get("url"):
        problems.append("plan.job.url missing")
    for i, f in enumerate(plan.get("fields", [])):
        label = str(f.get("label") or f"field {i}")
        if FORBIDDEN_FIELD.search(label) or FORBIDDEN_FIELD.search(str(f.get("value") or "")):
            problems.append(f"STOP - possible scam: the form asks for '{label}' (payment / passport / ID / bank details are never entered)")
            continue
        kind = f.get("kind", "fill")
        if not f.get("ref"):
            problems.append(f"'{label}': no element ref from the page snapshot")
        if kind == "upload":
            if str(Path(str(f.get("value"))).resolve()) not in allowed_uploads:
                problems.append(f"'{label}': only the compiled CV and cover letter PDFs may be uploaded")
            continue
        value = f.get("value")
        if value in (None, ""):
            problems.append(f"ASK USER - '{label}': no answer in the profile; ask the user, never invent one")
            continue
        quote = f.get("source_quote")
        if not quote or norm(quote) not in profile_norm:
            problems.append(f"'{label}': value must quote the profile verbatim (source_quote not found in CLAUDE.md / 01-candidate-profile.md)")
        elif norm(value) not in norm(quote) and not f.get("derived_from_quote_confirmed_by_user"):
            problems.append(f"ASK USER - '{label}': '{value}' is not stated in the quoted profile line; confirm it with the user")
    if not plan.get("submit_ref"):
        problems.append("plan.submit_ref missing (the final Submit control, recorded but not clicked by fill)")
    return problems


def review_hash(plan: dict) -> str:
    material = json.dumps({"url": plan.get("job", {}).get("url"), "fields": [(f.get("label"), f.get("ref"), f.get("kind", "fill"), f.get("value")) for f in plan.get("fields", [])], "submit_ref": plan.get("submit_ref")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def playwright_runner(session: str) -> Runner:
    def run(args: list[str]) -> str:
        cmd = ["playwright-cli", f"-s={session}", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            raise Refused(f"playwright-cli {args[0]} failed: {(proc.stderr or proc.stdout).strip()[:300]}")
        return proc.stdout

    return run


def open_browser(runner: Runner, url: str) -> None:
    """Headed, persistent profile in .browser-profile/. The user logs in by hand."""
    if not re.match(r"^https?://", url):
        raise Refused("only http(s) URLs are opened")
    runner(["open", url, "--headed", "--persistent", f"--profile={BROWSER_PROFILE}"])


# Where each login portal starts its sign-in. Anything else opens the portal's home page.
LOGIN_PAGES = {
    "linkedin.com": "https://www.linkedin.com/login",
    "jobstreet.com": "https://id.jobstreet.com/",
    "jobsdb.com": "https://th.jobsdb.com/",
    "seek.com.au": "https://www.seek.com.au/",
    "glints.com": "https://glints.com/id/login",
    "kalibrr.com": "https://www.kalibrr.com/login",
    "indeed.com": "https://secure.indeed.com/auth",
    "wellfound.com": "https://wellfound.com/login",
    "powertofly.com": "https://powertofly.com/",
}


def login(runner: Runner, portal: str) -> dict:
    """Open a portal's sign-in page in the persistent Playwright profile for the user.

    The user types their own credentials and 2FA in the headed window; this
    tool never reads, types or saves them and never exports cookies or state.
    The login then persists in .browser-profile/ for later /submit runs.
    """
    host = portal.lower().strip()
    host = host[4:] if host.startswith("www.") else host
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host):
        raise Refused(f"'{portal}' is not a portal host name (e.g. linkedin.com)")
    url = LOGIN_PAGES.get(host, f"https://{host}/")
    open_browser(runner, url)
    return {"status": "login_window_open", "portal": host, "url": url, "profile": str(BROWSER_PROFILE),
            "next": "Sign in yourself in the browser window (password, 2FA, CAPTCHA). Tell Claude when done; nothing is typed or saved for you."}


def fill(plan: dict, runner: Runner, *, screenshots: Path = SCREENSHOTS, profile: str | None = None) -> dict:
    """Fill every field, screenshot, and STOP. Never clicks plan['submit_ref']."""
    problems = validate_plan(plan, profile)
    if problems:
        raise Refused("plan refused:\n- " + "\n- ".join(problems))
    snapshot = runner(["snapshot"])
    if LOGIN_WALL.search(snapshot):
        raise Refused("PAUSE - a login, 2FA or CAPTCHA page is showing. Handle it yourself in the browser window, then run fill again.")
    for f in plan["fields"]:
        kind = f.get("kind", "fill")
        if f["ref"] == plan["submit_ref"]:
            raise Refused("a field targets the submit control; refusing")
        if kind == "upload":
            runner(["click", f["ref"]])
            runner(["upload", str(Path(str(f["value"])).resolve())])  # playwright-cli wants absolute paths
        elif kind == "select":
            runner(["select", f["ref"], str(f["value"])])
        elif kind == "check":
            runner(["check", f["ref"]])
        else:
            runner(["fill", f["ref"], str(f["value"])])
    screenshots.mkdir(parents=True, exist_ok=True)
    shot = screenshots / f"{slug(plan['job'].get('company', ''))}_{slug(plan['job'].get('role', ''))}_review.png"
    runner(["screenshot", f"--filename={shot}"])
    h = review_hash(plan)
    return {
        "status": "filled_waiting_for_user",
        "review_hash": h,
        "screenshot": str(shot),
        "fields": [{"label": f.get("label"), "value": f.get("value") if f.get("kind") != "upload" else Path(str(f["value"])).name} for f in plan["fields"]],
        "next": "Show the user every field and the screenshot. Run submit only after an explicit 'yes'.",
    }


def submit(plan: dict, runner: Runner, *, confirm: str, given_hash: str, mode: str, ledger: Path = LEDGER,
           tracker: Path = TRACKER, screenshots: Path = SCREENSHOTS, now: datetime | None = None) -> dict:
    """The one place the final Submit is clicked - only after an explicit yes on this exact plan."""
    if confirm != "yes":
        raise Refused("not submitted: the user has not said an explicit 'yes'")
    if given_hash != review_hash(plan):
        raise Refused("not submitted: the plan changed after the user reviewed it; run fill again and re-confirm")
    if mode == "fill_only":
        raise Refused("this portal is fill-only: the user clicks Submit themselves, then run `record --user-confirmed yes`")
    job = plan["job"]
    if already_submitted(ledger, job.get("company", ""), job.get("role", ""), job.get("url")):
        raise Refused("already submitted - never submit twice")
    runner(["click", plan["submit_ref"]])
    screenshots.mkdir(parents=True, exist_ok=True)
    shot = screenshots / f"{slug(job.get('company', ''))}_{slug(job.get('role', ''))}_confirmation.png"
    runner(["screenshot", f"--filename={shot}"])
    return record(job.get("company", ""), job.get("role", ""), job.get("url"), plan.get("channel", "ats_form"), str(shot),
                  ledger=ledger, tracker=tracker, now=now)


def record(company: str, role: str, url: str | None, channel: str, screenshot: str | None, *, ledger: Path = LEDGER,
           tracker: Path = TRACKER, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if already_submitted(ledger, company, role, url):
        raise Refused("already recorded as submitted")
    rel_shot = None
    if screenshot:
        try:
            rel_shot = str(Path(screenshot).resolve().relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel_shot = Path(screenshot).name
    note = f"{now.date().isoformat()} submitted via {channel}" + (f" - screenshot {rel_shot}" if rel_shot else "")
    update_tracker(tracker, company, role, channel, note)
    entry = {"company": company, "role": role, "url": url, "portal": portal_key(url), "channel": channel,
             "screenshot": rel_shot, "submitted_at": now.isoformat(timespec="seconds")}
    add_ledger(ledger, entry)
    return {"status": "recorded", **entry}


# ---------------------------------------------------------------- email

def email_draft(title: str, to: str, posting_text: str, body: str, cv: Path, cover: Path,
                sender: str | None, out: Path) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", to):
        raise Refused(f"'{to}' is not an email address")
    if to.lower() not in posting_text.lower():
        raise Refused(f"{to} does not appear in the posting text; only the posting's own apply address is used")
    for f in (cv, cover):
        if not f.is_file() or f.suffix.lower() != ".pdf":
            raise Refused(f"attachment {f} must be an existing compiled PDF")
        if FORBIDDEN_FIELD.search(f.name):
            raise Refused(f"refusing to attach {f.name}: ID/passport documents are never sent")
    msg = EmailMessage()
    msg["Subject"] = f"Application: {title} - Muhammad Ilham Ghazali"
    msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["X-Unsent"] = "1"  # opens as a draft in mail clients
    msg.set_content(body.strip() + "\n")
    for f in (cv, cover):
        msg.add_attachment(f.read_bytes(), maintype="application", subtype="pdf", filename=f.name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(msg))
    return {"status": "draft_saved", "eml": str(out), "to": to, "subject": msg["Subject"], "attachments": [cv.name, cover.name],
            "next": "Show the draft to the user. Send only after an explicit 'yes', then run record --channel email --user-confirmed yes."}


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Guards for /submit")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--company", required=True)
    c.add_argument("--role", required=True)
    c.add_argument("--key")
    c.add_argument("--job-file", type=Path)
    for name in ("fill", "submit"):
        s = sub.add_parser(name)
        s.add_argument("--plan", type=Path, required=True)
        s.add_argument("--session", default="submit")
        if name == "submit":
            s.add_argument("--review-hash", required=True)
            s.add_argument("--confirm", required=True)
            s.add_argument("--mode", choices=["fill_only", "confirm_then_click"], required=True)
    lg = sub.add_parser("login")
    lg.add_argument("--portal", required=True, help="host from the Needs login list, e.g. linkedin.com")
    lg.add_argument("--session", default="submit")
    o = sub.add_parser("open")
    o.add_argument("--url", required=True)
    o.add_argument("--session", default="submit")
    r = sub.add_parser("record")
    r.add_argument("--company", required=True)
    r.add_argument("--role", required=True)
    r.add_argument("--url")
    r.add_argument("--channel", required=True)
    r.add_argument("--screenshot")
    r.add_argument("--user-confirmed", required=True)
    e = sub.add_parser("email-draft")
    for a in ("--title", "--to"):
        e.add_argument(a, required=True)
    e.add_argument("--from", dest="sender")
    for a in ("--posting-file", "--body-file", "--cv", "--cover", "--out"):
        e.add_argument(a, type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == "check":
            job = load_json(args.job_file, None) if args.job_file else None
            result = check(args.company, args.role, key=args.key, job=job)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["allowed"] else 3
        if args.cmd == "login":
            print(json.dumps(login(playwright_runner(args.session), args.portal), ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "open":
            open_browser(playwright_runner(args.session), args.url)
            print(json.dumps({"status": "opened", "profile": str(BROWSER_PROFILE), "next": "log in yourself if the portal asks; then snapshot"}))
            return 0
        if args.cmd == "fill":
            print(json.dumps(fill(load_json(args.plan, {}), playwright_runner(args.session)), ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "submit":
            out = submit(load_json(args.plan, {}), playwright_runner(args.session), confirm=args.confirm,
                         given_hash=args.review_hash, mode=args.mode)
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "record":
            if args.user_confirmed != "yes":
                raise Refused("record needs --user-confirmed yes (the user confirmed the application was sent)")
            print(json.dumps(record(args.company, args.role, args.url, args.channel, args.screenshot), ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "email-draft":
            out = email_draft(args.title, args.to, args.posting_file.read_text(encoding="utf-8"),
                              args.body_file.read_text(encoding="utf-8"), args.cv, args.cover, args.sender, args.out)
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
    except Refused as exc:
        print(json.dumps({"refused": str(exc), "code": "REFUSED"}, ensure_ascii=False), file=sys.stderr)
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
