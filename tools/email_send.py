#!/usr/bin/env python3
"""The email queue behind /autopilot and /submit: one approval, then paced sends.

Run from the repo root:
    python tools/email_send.py verify  --to ADDR --posting-file F --company C [--url U] [--apply-url U]
    python tools/email_send.py enqueue --item item.json --body-file B --posting-file F --cv cv.pdf [--cover c.pdf]
                                       [--draft-file D] [--allow "value the user gave"]
    python tools/email_send.py table                     # the table the user approves
    python tools/email_send.py approve --reply "<the user's exact reply>"
    python tools/email_send.py next [--with-base64]      # paced; hands out one approved email
    python tools/email_send.py send-next                 # same, then sends it over SMTP (see Transports)
    python tools/email_send.py mark-sent --id ID --message-id M
    python tools/email_send.py mark-failed --id ID --reason R
    python tools/email_send.py status

Hard guarantees, enforced here rather than left to the model:
- An address is sent to only when it appears in the visible text of the posting
  (posting_guard.py's cleaned output), not on an instruction-like line, is not a
  free-mail address, and its domain matches the employer or a known recruiter
  (tools/data/recruiter_domains.json). Anything else is held for review.
- The body passes the claims check against the profile; a humanized body must
  add nothing the draft did not say. A problem holds the email for review.
- Nothing goes out without `approve`: "yes", "no" or "exclude 2,5". Any other
  reply, or none, sends nothing. Approval pins the address, subject, body and
  attachments; a later change voids it.
- At most 15 emails a day, 30-90 s apart. One send per item: an email handed out
  by `next` is never handed out again, even when the run dies before mark-sent.
- Attachments are the compiled PDFs only.

Transports. `next` hands the email to the Gmail connector
(mcp__claude_ai_Gmail__send_message). That connector takes attachments as base64
text inside the tool call, which for two PDFs is about 200 KB the model must read
and repeat exactly. With GMAIL_SMTP_USER and GMAIL_APP_PASSWORD set (a Google app
password, environment only, never printed), `send-next` sends the same email from
this process instead. Same queue, same guarantees.

Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import smtplib
import ssl
import sys
import time
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freelance_guard as fg  # noqa: E402
import submit_guard as sg  # noqa: E402
from job_dedup import norm_company  # noqa: E402
from job_rules import ATS_HOSTS, INJECTION, LOGIN_HOSTS  # noqa: E402
from posting_guard import INSTRUCTION_PATTERNS, guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "job_scraper" / "email_queue.json"
RECRUITERS = Path(__file__).resolve().parent / "data" / "recruiter_domains.json"
DAILY_LIMIT = 15
PACE_SECONDS = (30, 90)
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.id", "ymail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "gmx.de", "mail.com", "zoho.com", "yandex.com",
    "qq.com", "163.com", "naver.com",
}
# Words too common in company names to identify an employer's domain on their own.
GENERIC_TOKENS = {"tech", "technology", "technologies", "software", "digital", "group", "labs", "solutions", "systems", "global",
                  "indonesia", "asia", "studio", "studios", "apps", "mobile", "consulting", "services", "company", "international"}
OPEN = ("pending", "approved")
Sleeper = Callable[[float], None]
SmtpSend = Callable[[EmailMessage, str, str], None]


def load_queue(path: Path = QUEUE) -> dict:
    data = sg.load_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("items", [])
    return data


def _domain_root(domain: str) -> str:
    """`careers.acme.co.id` -> `acme`."""
    parts = domain.lower().split(".")
    if len(parts) > 2 and len(parts[-1]) == 2 and len(parts[-2]) <= 3:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else domain


def _employer_host(url: str | None) -> str | None:
    """The host of a posting URL when it is the employer's own site, not a portal or ATS."""
    host = sg.host_of(url)
    if not host or any(host == h or host.endswith("." + h) for h in (*ATS_HOSTS, *LOGIN_HOSTS)):
        return None
    return host


def employer_matches(domain: str, company: str | None, urls: tuple[str | None, ...] = ()) -> bool:
    """Exact, not fuzzy: `acme-careers.xyz` does not match Acme, so a look-alike goes to review."""
    root = re.sub(r"[^a-z0-9]", "", _domain_root(domain))
    name = norm_company(company or "")
    tokens = [t for t in re.split(r"[^a-z0-9]+", name) if t]
    if root and tokens and (root == "".join(tokens) or (root in tokens and len(root) >= 4 and root not in GENERIC_TOKENS)):
        return True
    for url in urls:
        host = _employer_host(url)
        if host and _domain_root(host) == _domain_root(domain):
            return True
    return False


def load_recruiters(path: Path = RECRUITERS) -> set[str]:
    data = sg.load_json(path, {})
    return {str(d).lower() for d in (data.get("domains") or [])} if isinstance(data, dict) else set()


def verify_address(to: str, posting_text: str, company: str | None, urls: tuple[str | None, ...] = (), *,
                   recruiters: set[str] | None = None) -> dict:
    """status: ok | needs_review | rejected. `rejected` is an address that must never be mailed."""
    to = (to or "").strip()
    if not ADDRESS.fullmatch(to):
        return {"status": "rejected", "reason": f"'{to}' is not an email address"}
    cleaned, _ = guard(posting_text, "auto")
    wanted = to.lower()
    visible = {a.lower() for a in ADDRESS.findall(cleaned)}
    if wanted not in visible:
        hidden = wanted in {a.lower() for a in ADDRESS.findall(posting_text)}
        return {"status": "rejected", "reason": f"{to} appears only in a hidden part of the posting" if hidden else f"{to} does not appear in the posting"}
    for line in cleaned.splitlines():
        if wanted in line.lower() and (INJECTION.search(line) or any(rx.search(line) for rx in INSTRUCTION_PATTERNS)):
            return {"status": "rejected", "reason": f"{to} sits on an instruction-like line of the posting (possible injection)"}
    domain = wanted.split("@", 1)[1]
    if domain in FREE_MAIL:
        return {"status": "needs_review", "reason": f"free-mail address ({domain}) for {company or 'this employer'}"}
    if employer_matches(domain, company, urls):
        return {"status": "ok", "reason": "domain matches the employer"}
    known = recruiters if recruiters is not None else load_recruiters()
    if domain in known or _domain_root(domain) in {_domain_root(k) for k in known}:
        return {"status": "ok", "reason": "known recruiter domain"}
    return {"status": "needs_review", "reason": f"domain {domain} does not match {company or 'the employer'} and is not a known recruiter"}


# ---------------------------------------------------------------- enqueue

def item_id(item: dict) -> str:
    return hashlib.sha256(f"{item.get('type')}|{item.get('url')}|{item.get('company')}|{item.get('title')}".encode("utf-8")).hexdigest()[:12]


def _hash_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(entry: dict) -> str:
    material = [entry["to"], entry["subject"], entry["body"], *[_hash_file(a) for a in entry["attachments"]]]
    return hashlib.sha256("\x00".join(material).encode("utf-8")).hexdigest()


def duplicate_reason(item: dict, *, job_tracker: Path = sg.TRACKER, ledger: Path = sg.LEDGER, gig_tracker: Path = fg.TRACKER) -> str | None:
    if item.get("type") == "gig":
        return "already proposed to this gig" if fg.already_proposed(gig_tracker, item) else None
    if sg.already_submitted(ledger, item.get("company") or "", item.get("title") or "", item.get("url")):
        return "already submitted"
    if job_tracker.is_file():
        _, rows, _ = sg.read_tracker(job_tracker)
        if any(sg.norm(r.get("status")) in sg.SUBMITTED for r in sg.find_rows(rows, item.get("company") or "", item.get("title") or "")):
            return "already applied (tracker)"
    return None


def enqueue(item: dict, body: str, posting_text: str, cv: str, cover: str | None = None, *, draft: str | None = None, allow: list[str] | None = None,
            queue: Path = QUEUE, profile: str | None = None, recruiters: set[str] | None = None, job_tracker: Path = sg.TRACKER,
            ledger: Path = sg.LEDGER, gig_tracker: Path = fg.TRACKER) -> dict:
    """Run every check and queue the email: `pending` when clean, `needs_review` with reasons when not."""
    data = load_queue(queue)
    iid = item_id(item)
    if any(e["id"] == iid and e["status"] in ("sent", "sending") for e in data["items"]):
        raise sg.Refused("this email was already handed out or sent - never apply twice")
    data["items"] = [e for e in data["items"] if e["id"] != iid]
    reasons: list[str] = []
    dup = duplicate_reason(item, job_tracker=job_tracker, ledger=ledger, gig_tracker=gig_tracker)
    if dup:
        reasons.append(dup)
    to = item.get("to") or ""
    verdict = verify_address(to, posting_text, item.get("company"), (item.get("url"), item.get("apply_url")), recruiters=recruiters)
    if verdict["status"] != "ok":
        reasons.append(f"address: {verdict['reason']}")
    attachments = [str(Path(p).resolve()) for p in (cv, cover) if p]
    for path in attachments:
        if not Path(path).is_file() or Path(path).suffix.lower() != ".pdf":
            reasons.append(f"attachment {Path(path).name} must be an existing compiled PDF")
        elif sg.FORBIDDEN_FIELD.search(Path(path).name):
            reasons.append(f"refusing to attach {Path(path).name}: ID/passport documents are never sent")
    if item.get("type") != "gig" and not cover:
        reasons.append("a job application needs both the CV and the cover letter PDF")
    posting_clean, _ = guard(posting_text, "auto")
    allowed = allow or []
    if draft is not None and draft.strip() != body.strip():
        reasons += [f"claims: {p}" for p in fg.humanizer_check(draft, body, posting_clean, allowed, profile)]
    else:
        reasons += [f"claims: {p}" for p in fg.claims_check(body, posting_clean, allowed, profile)]
    label = "Proposal" if item.get("type") == "gig" else "Application"
    entry = {
        "id": iid, "type": item.get("type") or "job", "company": item.get("company"), "title": item.get("title"), "url": item.get("url"),
        "platform": item.get("platform"), "gig_id": item.get("gig_id"), "idr_monthly_equiv": item.get("idr_monthly_equiv"),
        "to": to, "subject": f"{label}: {item.get('title')} - Muhammad Ilham Ghazali", "body": body.strip() + "\n", "attachments": attachments,
        "status": "needs_review" if reasons else "pending", "reasons": reasons, "rejected_address": verdict["status"] == "rejected",
        "queued_on": date.today().isoformat(),
    }
    data["items"].append(entry)
    sg.save_json(queue, data)
    return {k: entry[k] for k in ("id", "status", "reasons", "to", "subject")}


# ---------------------------------------------------------------- approval

def pending(data: dict, only: str | None = None) -> list[dict]:
    return [e for e in data["items"] if e["status"] == "pending" and only in (None, e["id"])]


def table(queue: Path = QUEUE, only: str | None = None) -> str:
    rows = pending(load_queue(queue), only)
    lines = ["| # | type | company/client | title | ≈ IDR/month | to-address | subject |", "|---|---|---|---|---|---|---|"]
    for n, e in enumerate(rows, 1):
        idr = f"{e['idr_monthly_equiv']:,}" if isinstance(e.get("idr_monthly_equiv"), (int, float)) else "-"
        lines.append(f"| {n} | {e['type']} | {e.get('company') or '-'} | {e.get('title')} | {idr} | {e['to']} | {e['subject']} |")
    return "\n".join(lines)


def parse_reply(reply: str | None, count: int) -> set[int] | None:
    """The numbers (1-based) to send, or None for nothing. Only an unambiguous reply sends anything."""
    text = (reply or "").strip().lower().rstrip(".!")
    if text == "yes":
        return set(range(1, count + 1))
    m = re.fullmatch(r"(?:yes\s*,?\s*)?exclude\s+(\d+(?:\s*,\s*\d+)*)", text)
    if not m:
        return None
    excluded = {int(n) for n in re.split(r"\s*,\s*", m.group(1))}
    if any(n < 1 or n > count for n in excluded):
        return None
    return set(range(1, count + 1)) - excluded


def approve(reply: str | None, *, queue: Path = QUEUE, dry_run: bool = False, only: str | None = None) -> dict:
    """The only gate to sending. Anything but a clear yes or exclude list sends nothing.
    `only` is /submit's single item: other queued emails are left as they are."""
    if dry_run:
        raise sg.Refused("--dry-run: nothing is sent")
    data = load_queue(queue)
    rows = pending(data, only)
    chosen = parse_reply(reply, len(rows))
    for n, e in enumerate(rows, 1):
        if chosen is None:
            e["status"] = "not_sent"
        elif n in chosen:
            e["status"] = "approved"
            e["approved_fingerprint"] = fingerprint(e)
        else:
            e["status"] = "excluded"
    sg.save_json(queue, data)
    return {"approved": [e["id"] for e in rows if e["status"] == "approved"], "not_sent": [e["id"] for e in rows if e["status"] != "approved"]}


# ---------------------------------------------------------------- sending

def sent_today(data: dict, today: date) -> int:
    return sum(1 for e in data["items"] if e["status"] in ("sent", "sending") and str(e.get("sent_at", "")).startswith(today.isoformat()))


def next_email(*, queue: Path = QUEUE, now: Callable[[], datetime] = datetime.now, sleeper: Sleeper = time.sleep, job_tracker: Path = sg.TRACKER,
               ledger: Path = sg.LEDGER, gig_tracker: Path = fg.TRACKER, with_base64: bool = False) -> dict:
    """Hand out one approved email, waiting out the 30-90 s pace first. Marks it `sending`: it never comes back."""
    data = load_queue(queue)
    approved = [e for e in data["items"] if e["status"] == "approved"]
    if not approved:
        return {"status": "done"}
    if sent_today(data, now().date()) >= DAILY_LIMIT:
        return {"status": "daily_limit", "limit": DAILY_LIMIT, "waiting": [e["id"] for e in approved],
                "next": "Stop for today. The remaining approved emails stay queued; rerun tomorrow."}
    entry = approved[0]
    item = {"type": entry["type"], "company": entry.get("company"), "title": entry.get("title"), "url": entry.get("url"),
            "platform": entry.get("platform"), "gig_id": entry.get("gig_id")}
    dup = duplicate_reason(item, job_tracker=job_tracker, ledger=ledger, gig_tracker=gig_tracker)
    if dup or entry.get("approved_fingerprint") != fingerprint(entry):
        entry["status"] = "needs_review"
        entry["reasons"] = [dup or "the email changed after it was approved"]
        sg.save_json(queue, data)
        return {"status": "held", "id": entry["id"], "reasons": entry["reasons"]}
    last = data.get("last_sent_at")
    if last:
        wait = random.uniform(*PACE_SECONDS) - (now() - datetime.fromisoformat(last)).total_seconds()
        if wait > 0:
            sleeper(wait)
    stamp = now().isoformat(timespec="seconds")
    entry.update(status="sending", sent_at=stamp)
    data["last_sent_at"] = stamp
    sg.save_json(queue, data)
    out = {"status": "ready", "id": entry["id"], "to": entry["to"], "subject": entry["subject"], "body": entry["body"],
           "attachments": [{"filename": Path(a).name, "path": a, "mimeType": "application/pdf", "bytes": Path(a).stat().st_size} for a in entry["attachments"]],
           "transport": "smtp" if smtp_credentials() else "gmail_connector"}
    if with_base64:
        for a in out["attachments"]:
            a["content"] = base64.b64encode(Path(a["path"]).read_bytes()).decode("ascii")
    return out


def mark_sent(iid: str, message_id: str, *, queue: Path = QUEUE, now: Callable[[], datetime] = datetime.now, job_tracker: Path = sg.TRACKER,
              ledger: Path = sg.LEDGER, gig_tracker: Path = fg.TRACKER) -> dict:
    data = load_queue(queue)
    entry = next((e for e in data["items"] if e["id"] == iid), None)
    if entry is None or entry["status"] != "sending":
        raise sg.Refused(f"{iid} is not an email handed out by next")
    entry.update(status="sent", message_id=message_id)
    sg.save_json(queue, data)
    warning = None
    try:
        if entry["type"] == "gig":
            fg.record({"title": entry.get("title"), "platform": entry.get("platform"), "gig_id": entry.get("gig_id"), "url": entry.get("url")}, "", 0, None,
                      tracker=gig_tracker, today=now().date(), status="applied", channel="email", message_id=message_id)
        else:
            sg.record(entry.get("company") or "", entry.get("title") or "", entry.get("url"), "email", None, ledger=ledger, tracker=job_tracker, message_id=message_id)
    except sg.Refused as exc:
        # The email is out; only the bookkeeping failed. Say so, never resend.
        warning = f"sent, but the tracker was not updated: {exc}. Run /outcome by hand."
    return {"status": "sent", "id": iid, "message_id": message_id, "warning": warning}


def mark_failed(iid: str, reason: str, *, queue: Path = QUEUE) -> dict:
    data = load_queue(queue)
    entry = next((e for e in data["items"] if e["id"] == iid), None)
    if entry is None or entry["status"] != "sending":
        raise sg.Refused(f"{iid} is not an email handed out by next")
    entry.update(status="failed", reasons=[reason[:300]])
    sg.save_json(queue, data)
    return {"status": "failed", "id": iid}


def smtp_credentials() -> tuple[str, str] | None:
    user, password = os.environ.get("GMAIL_SMTP_USER", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    return (user, password) if user and password else None


def _smtp_send(msg: EmailMessage, user: str, password: str) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as server:
        server.login(user, password)
        server.send_message(msg)


def send_next(*, queue: Path = QUEUE, sender: SmtpSend = _smtp_send, **kw) -> dict:
    """`next`, then send over SMTP from this process. A failure is recorded, never retried."""
    creds = smtp_credentials()
    if not creds:
        raise sg.Refused("GMAIL_SMTP_USER and GMAIL_APP_PASSWORD are not set; use next and the Gmail connector")
    out = next_email(queue=queue, **kw)
    if out["status"] != "ready":
        return out
    msg = EmailMessage()
    msg["Subject"], msg["To"], msg["From"] = out["subject"], out["to"], creds[0]
    msg["Message-ID"] = message_id = make_msgid()
    msg.set_content(out["body"])
    for a in out["attachments"]:
        msg.add_attachment(Path(a["path"]).read_bytes(), maintype="application", subtype="pdf", filename=a["filename"])
    try:
        sender(msg, *creds)
    except (smtplib.SMTPException, OSError) as exc:
        # The class name only: an SMTP error text can echo what the login sent.
        return mark_failed(out["id"], f"SMTP send failed: {type(exc).__name__}", queue=queue)
    tracker_kw = {k: kw[k] for k in ("now", "job_tracker", "ledger", "gig_tracker") if k in kw}
    return mark_sent(out["id"], message_id, queue=queue, **tracker_kw)


def status(queue: Path = QUEUE) -> dict:
    data = load_queue(queue)
    return {"items": [{k: e.get(k) for k in ("id", "type", "company", "title", "to", "status", "reasons", "message_id")} for e in data["items"]]}


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Email queue for /autopilot and /submit")
    p.add_argument("--queue", type=Path, default=QUEUE)
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--to", required=True)
    v.add_argument("--posting-file", type=Path, required=True)
    v.add_argument("--company")
    v.add_argument("--url")
    v.add_argument("--apply-url")
    e = sub.add_parser("enqueue")
    e.add_argument("--item", type=Path, required=True)
    e.add_argument("--body-file", type=Path, required=True)
    e.add_argument("--posting-file", type=Path, required=True)
    e.add_argument("--cv", required=True)
    e.add_argument("--cover")
    e.add_argument("--draft-file", type=Path, help="the text before the humanizer; the body may add nothing to it")
    e.add_argument("--allow", action="append", default=[])
    sub.add_parser("table").add_argument("--only")
    a = sub.add_parser("approve")
    a.add_argument("--reply", default="")
    a.add_argument("--only")
    a.add_argument("--dry-run", action="store_true")
    n = sub.add_parser("next")
    n.add_argument("--with-base64", action="store_true")
    sub.add_parser("send-next")
    m = sub.add_parser("mark-sent")
    m.add_argument("--id", required=True)
    m.add_argument("--message-id", required=True)
    f = sub.add_parser("mark-failed")
    f.add_argument("--id", required=True)
    f.add_argument("--reason", required=True)
    sub.add_parser("status")
    args = p.parse_args(argv)

    def emit(obj) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    try:
        if args.cmd == "verify":
            out = verify_address(args.to, args.posting_file.read_text(encoding="utf-8"), args.company, (args.url, args.apply_url))
            emit(out)
            return 0 if out["status"] == "ok" else 3
        if args.cmd == "enqueue":
            item = sg.load_json(args.item, None)
            if not isinstance(item, dict):
                raise sg.Refused(f"{args.item} is not an item JSON object")
            emit(enqueue(item, args.body_file.read_text(encoding="utf-8"), args.posting_file.read_text(encoding="utf-8"), args.cv, args.cover,
                         draft=args.draft_file.read_text(encoding="utf-8") if args.draft_file else None, allow=args.allow, queue=args.queue))
        elif args.cmd == "table":
            print(table(args.queue, args.only))
        elif args.cmd == "approve":
            emit(approve(args.reply, queue=args.queue, dry_run=args.dry_run, only=args.only))
        elif args.cmd == "next":
            emit(next_email(queue=args.queue, with_base64=args.with_base64))
        elif args.cmd == "send-next":
            emit(send_next(queue=args.queue))
        elif args.cmd == "mark-sent":
            emit(mark_sent(args.id, args.message_id, queue=args.queue))
        elif args.cmd == "mark-failed":
            emit(mark_failed(args.id, args.reason, queue=args.queue))
        elif args.cmd == "status":
            emit(status(args.queue))
    except sg.Refused as exc:
        print(json.dumps({"refused": str(exc), "code": "REFUSED"}, ensure_ascii=False), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
