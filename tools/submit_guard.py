#!/usr/bin/env python3
"""The deterministic half of /submit: preconditions, the duplicate guard,
tracker recording and email drafts. /submit sends email applications only (see
tools/email_send.py); it never opens a browser and never fills a form. For any
other apply method it prints the manual checklist from tools/autopilot.py.

Run from the repo root (see .claude/commands/submit.md for the full flow):

    python tools/submit_guard.py check   --company C --role R (--key K | --job-file job.json)
    python tools/submit_guard.py record  --company C --role R --url U --channel CH [--message-id M] --user-confirmed yes
    python tools/submit_guard.py email-draft --title T --to ADDR --posting-file F
                                  --body-file B --cv cv.pdf --cover cover.pdf --out draft.eml

Hard guarantees, enforced here rather than left to the model:
- No submission unless /apply produced both PDFs, the hard rules put the job in
  `confirmed`, and safety_screening is `verified_low_concern`.
- One submission per job (tracker status + ledger), max 10 per portal per day.
- Passport/ID or bank documents are never attached (FORBIDDEN_FIELD).
Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_rates import DEFAULT_CACHE, load_rates  # noqa: E402
from job_rules import apply_method, evaluate_job  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "job_search_tracker.csv"
SEEN = ROOT / "job_scraper" / "seen_jobs.json"
LEDGER = ROOT / "job_scraper" / "submissions.json"
PROFILE_FILES = [ROOT / "CLAUDE.md", ROOT / ".claude" / "skills" / "job-application-assistant" / "01-candidate-profile.md"]
DAILY_LIMIT_PER_PORTAL = 10
SUBMITTED = {"applied", "interview", "offer", "hired", "rejected", "no_response", "no response", "offer_declined", "offer declined", "withdrawn"}
FORBIDDEN_FIELD = re.compile(
    r"(credit\s*card|card\s*number|cvv|cvc|expiry|payment|pay\s+now|deposit|bank\s*(account|details|transfer)|iban|"
    r"passport|national\s*id|\bktp\b|\bnik\b|id\s*card|ssn|social\s+security|tax\s*id|npwp|driver'?s?\s+licen[cs]e)",
    re.I,
)


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


def update_tracker(path: Path, company: str, role: str, channel: str, note: str, *, status: str = "applied",
                   sent_on: str | None = None, force_channel: bool = False) -> None:
    """Set `status` on the one matching row and append a dated note.

    Same rules as /outcome Step 4: touch only status/notes (channel when empty
    or forced, date when `sent_on` is the real submission date), never
    restructure, never quote, never touch other rows.
    """
    header, rows, newline = read_tracker(path)
    matches = find_rows(rows, company, role)
    if len(matches) != 1:
        raise Refused(f"expected exactly one tracker row for {company} / {role}, found {len(matches)}")
    row = matches[0]
    clean = re.sub(r"[,\"\r\n]+", " ", note).strip()
    row["status"] = status
    if sent_on and "date" in row:
        row["date"] = sent_on
    if "channel" in row and (force_channel or not (row.get("channel") or "").strip()):
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
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "apply_method": method["method"],
        "apply_email": method.get("email"),
        "portal": portal,
        "url": url,
        "cv_pdf": str(cv_pdf) if cv_pdf else None,
        "cover_pdf": str(cover_pdf) if cover_pdf else None,
        "section": verdict["section"] if verdict else None,
        "safety_screening": verdict["safety_screening"] if verdict else None,
    }


def profile_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in PROFILE_FILES if p.is_file())


def record(company: str, role: str, url: str | None, channel: str, screenshot: str | None = None, *, ledger: Path = LEDGER,
           tracker: Path = TRACKER, now: datetime | None = None, message_id: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if already_submitted(ledger, company, role, url):
        raise Refused("already recorded as submitted")
    rel_shot = None
    if screenshot:
        try:
            rel_shot = str(Path(screenshot).resolve().relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel_shot = Path(screenshot).name
    note = f"{now.date().isoformat()} submitted via {channel}" + (f" - screenshot {rel_shot}" if rel_shot else "") + (f" - message id {message_id}" if message_id else "")
    # An email goes out on this day through this channel; a hand-recorded row keeps /outcome's rules.
    update_tracker(tracker, company, role, channel, note, sent_on=now.date().isoformat() if message_id else None, force_channel=bool(message_id))
    entry = {"company": company, "role": role, "url": url, "portal": portal_key(url), "channel": channel,
             "screenshot": rel_shot, "message_id": message_id, "submitted_at": now.isoformat(timespec="seconds")}
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
    r = sub.add_parser("record")
    r.add_argument("--company", required=True)
    r.add_argument("--role", required=True)
    r.add_argument("--url")
    r.add_argument("--channel", required=True)
    r.add_argument("--screenshot")
    r.add_argument("--message-id")
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
        if args.cmd == "record":
            if args.user_confirmed != "yes":
                raise Refused("record needs --user-confirmed yes (the user confirmed the application was sent)")
            print(json.dumps(record(args.company, args.role, args.url, args.channel, args.screenshot, message_id=args.message_id), ensure_ascii=False, indent=2))
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
