#!/usr/bin/env python3
"""The deterministic half of /autopilot, and the merged jobs + gigs view for /scrape and /rank.

Run from the repo root (see .claude/commands/autopilot.md for the full flow):
    python tools/autopilot.py scope [--jobs-only|--gigs-only]      # which skills a /scrape run uses
    python tools/autopilot.py combine --gigs <gig_rules output> [--jobs-only|--gigs-only] --out combined.json
    python tools/autopilot.py select --combined combined.json [--limit 20] [--max-items 200] [--dry-run] --out run.json
    python tools/autopilot.py next-item --run run.json             # the next item to prepare, in order
    python tools/autopilot.py mark --run run.json --id N --status prepared|failed|needs_review [--reason R] [--cv P] [--cover P] [--proposal P] [--apply-method M]
    python tools/autopilot.py finish --run run.json                # final statuses, trackers, manual checklists
    python tools/autopilot.py checklist --item item.json           # one manual checklist (/submit on a non-email job)
    python tools/autopilot.py report --run run.json

`idr_monthly_equiv` is the sort key jobs and gigs share: a job's
salary_idr_monthly_min; an hourly gig's IDR rate x 173; a fixed gig's IDR budget /
months (at least 1). Null is never auto-selected.

This module prepares and reports. It never opens a browser, never fills a form
and never sends anything: email goes through tools/email_send.py, one approval.
Trackers stay separate: job_search_tracker.csv for jobs, freelance_tracker.csv for gigs.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import email_send as es  # noqa: E402
import freelance_guard as fg  # noqa: E402
import submit_guard as sg  # noqa: E402
from gig_rules import proposed_keys, gig_keys, load_platforms  # noqa: E402
from job_dedup import canonical_url  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"
PROFILE = ROOT / "CLAUDE.md"
DEFAULT_LIMIT = 20
MAX_ITEMS = 200
MIN_FIT = 45  # 04-job-evaluation.md's Moderate Fit band: below it /rank does not shortlist either
SECTIONS = ("confirmed", "needs_verification", "manual_safety_review", "rejected")
GIG_SECTION = {"good_fits": "confirmed", "needs_budget_client_review": "needs_verification",
               "manual_safety_review": "manual_safety_review", "rejected": "rejected"}
# A rough budget for the report, from this workflow's shape. Not a measurement.
TOKEN_ESTIMATE = {"scrape": 40_000, "rank_per_item": 3_000, "apply": 80_000, "propose": 8_000, "email": 2_000}


class Refused(sg.Refused):
    pass


def only_flag(jobs_only: bool, gigs_only: bool) -> str | None:
    if jobs_only and gigs_only:
        raise Refused("--jobs-only and --gigs-only cannot be combined")
    return "job" if jobs_only else "gig" if gigs_only else None


# ---------------------------------------------------------------- /scrape scope

def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    return text[:end] if text.startswith("---") and end != -1 else ""


def scope(only: str | None = None, skills_dir: Path = SKILLS) -> dict:
    """What one /scrape run runs. Default both types; /gigs is `--gigs-only`. A disabled skill is listed, not run."""
    out = {"types": [t for t in ("job", "gig") if only in (None, t)], "job_skills": [], "gig_skills": [], "skipped_disabled": []}
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        fm = _frontmatter(path)
        kind = "gig" if re.search(r"^category:\s*freelance\b", fm, re.M) else "job"
        if only not in (None, kind):
            continue
        if re.search(r"^enabled:\s*false\b", fm, re.M):
            out["skipped_disabled"].append(path.parent.name)
        else:
            out[f"{kind}_skills"].append(path.parent.name)
    return out


# ---------------------------------------------------------------- the combined list

def job_row(key: str, entry: dict) -> dict:
    section = entry.get("rules_section") or "needs_verification"
    reasons = list(entry.get("rules_reasons") or [])
    for field, label in (("location_verdict", "location"), ("language_gate", "language")):
        if entry.get(field) == "FAIL" and section != "rejected":
            section = "rejected"
            reasons = [f"{label} FAIL" + (f": {entry['language_note']}" if field == "language_gate" and entry.get("language_note") else "")]
    return {"type": "job", "key": key, "title": entry.get("title"), "company": entry.get("company"), "url": entry.get("url"),
            "apply_url": entry.get("apply_url"), "section": section, "reasons": reasons, "safety_screening": entry.get("safety_screening"),
            "apply_method": entry.get("apply_method"), "to": entry.get("apply_email"), "idr_monthly_equiv": entry.get("salary_idr_monthly_min"),
            "fit_score": entry.get("rank_score"), "portal": entry.get("portal")}


def gig_row(gig: dict) -> dict:
    rules = gig.get("rules") or {}
    method = gig.get("apply_method") or "platform_proposal"
    return {"type": "gig", "key": f"{gig.get('platform')}:{gig.get('gig_id')}", "title": gig.get("title"), "company": gig.get("client_country") or "client",
            "url": gig.get("url"), "platform": gig.get("platform"), "gig_id": gig.get("gig_id"), "section": GIG_SECTION.get(rules.get("section"), "needs_verification"),
            "reasons": rules.get("reasons") or [], "safety_screening": gig.get("safety_screening"), "apply_method": method, "to": gig.get("apply_email"),
            "idr_monthly_equiv": rules.get("idr_monthly_equiv"), "fit_score": rules.get("fit_score"),
            "needs_budget_review": rules.get("idr_monthly_equiv") is None, "connects_or_bids_cost": gig.get("connects_or_bids_cost")}


def sort_key(row: dict) -> tuple:
    return (-(row.get("idr_monthly_equiv") or -1), -(row.get("fit_score") or 0), str(row.get("title") or ""))


def combine(*, seen: Path = sg.SEEN, gigs: dict | None = None, only: str | None = None, since: str | None = None) -> dict:
    """One list with a `type` column, in /rank's four sections. A hard-rule rejection stored on an old entry stays out."""
    since = since or date.today().isoformat()
    rows: list[dict] = []
    if only != "gig":
        for key, entry in (sg.load_json(seen, {}).get("seen") or {}).items():
            if not isinstance(entry, dict) or not entry.get("rules_section") or entry.get("type", "job") != "job":
                continue
            if entry.get("status") == "ranked" or str(entry.get("first_seen") or "") >= since:
                if entry.get("status") != "expired":
                    rows.append(job_row(key, entry))
    if only != "job" and gigs:
        for name in GIG_SECTION:
            rows += [gig_row(g) for g in (gigs.get("sections") or {}).get(name, [])]
    sections = {s: sorted((r for r in rows if r["section"] == s), key=sort_key) for s in SECTIONS}
    registry = (gigs or {}).get("vetted_networks") or load_platforms().get("vetted_networks", [])
    return {"sections": sections, "counts": {s: len(v) for s, v in sections.items()},
            "scraped": {t: sum(1 for r in rows if r["type"] == t) for t in ("job", "gig")},
            "vetted_networks": registry if only != "job" else []}


# ---------------------------------------------------------------- selection

def in_tracker(row: dict, *, job_tracker: Path, gig_tracker: Path) -> bool:
    """Every tracker row counts here, `ready_to_submit` and `drafted` included: never prepare twice."""
    if row["type"] == "gig":
        return any(k in proposed_keys(gig_tracker, include_prepared=True) for k in gig_keys(row))
    if not job_tracker.is_file():
        return False
    _, rows, _ = sg.read_tracker(job_tracker)
    if sg.find_rows(rows, row.get("company") or "", row.get("title") or ""):
        return True
    url = canonical_url(row.get("url"))
    return bool(url) and any(canonical_url(r.get("source")) == url for r in rows)


def select(combined: dict, *, limit: int = DEFAULT_LIMIT, max_items: int = MAX_ITEMS, only: str | None = None, dry_run: bool = False,
           min_fit: int = MIN_FIT, job_tracker: Path = sg.TRACKER, gig_tracker: Path = fg.TRACKER) -> dict:
    """Confirmed + verified_low_concern + not tracked + a known idr_monthly_equiv, highest first."""
    if limit < 1 or max_items < 1:
        raise Refused("--limit and --max-items must be positive")
    eligible, skipped = [], []
    for row in combined["sections"]["confirmed"]:
        if only not in (None, row["type"]):
            continue
        if row.get("safety_screening") != "verified_low_concern":
            reason = f"safety_screening is {row.get('safety_screening')}, not verified_low_concern"
        elif in_tracker(row, job_tracker=job_tracker, gig_tracker=gig_tracker):
            reason = "already in the tracker"
        elif row.get("idr_monthly_equiv") is None:
            reason = "no idr_monthly_equiv: needs budget review"
        elif row.get("fit_score") is not None and row["fit_score"] < min_fit:
            reason = f"fit score {row['fit_score']} below {min_fit}"
        else:
            eligible.append(row)
            continue
        skipped.append({**row, "skip_reason": reason})
    eligible.sort(key=sort_key)
    cap = min(limit, max_items)
    items = [{**row, "id": n, "status": "selected"} for n, row in enumerate(eligible[:cap], 1)]
    deferred = [{**row, "skip_reason": f"beyond the limit of {cap} this run"} for row in eligible[cap:]]
    listed = {s: [r for r in combined["sections"][s] if only in (None, r["type"])] for s in ("needs_verification", "manual_safety_review", "rejected")}
    return {"dry_run": dry_run, "items": items, "skipped": skipped + deferred, "listed": listed, "scraped": combined.get("scraped", {}),
            "vetted_networks": combined.get("vetted_networks", [])}


# ---------------------------------------------------------------- the prepare loop

def next_item(run: dict) -> dict | None:
    return next((i for i in run["items"] if i["status"] == "selected"), None)


def mark(run: dict, item_id: int, status: str, *, reason: str | None = None, cv: str | None = None, cover: str | None = None,
         proposal: str | None = None, apply_method: str | None = None) -> dict:
    """One item's result. A failure is a record, never an exception: the next item still runs."""
    if status not in ("prepared", "failed", "needs_review"):
        raise Refused(f"unknown status {status}")
    item = next((i for i in run["items"] if i["id"] == item_id), None)
    if item is None:
        raise Refused(f"no item {item_id} in this run")
    item["status"] = status
    updates = {"reason": reason, "cv": cv, "cover": cover, "proposal": proposal, "apply_method": apply_method}
    item.update({k: v for k, v in updates.items() if v})
    return item


# ---------------------------------------------------------------- manual checklist

def _profile_lines(*paths: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in paths if p.is_file())


def screening_answers(profile: str | None = None) -> list[dict]:
    """Copy-paste answers lifted from the profile, verbatim. Anything else is the user's to answer."""
    text = profile if profile is not None else _profile_lines(PROFILE, *sg.PROFILE_FILES)
    fields = [("Full name", "Name"), ("Location", "Location"), ("Email", "Email"), ("Phone", "Phone"), ("LinkedIn", "LinkedIn"), ("GitHub", "GitHub"),
              ("Portfolio", "Portfolio/Demos"), ("Availability", "Status")]
    out = []
    for label, key in fields:
        m = re.search(rf"^\s*- \*\*{re.escape(key)}:\*\*\s*(.+?)\s*$", text, re.M)
        if m:
            out.append({"question": label, "answer": m.group(1)})
    edu = re.search(r"^\s*- \*\*(Bachelor[^*]+)\*\*\s*(.*)$", text, re.M)
    if edu:
        out.append({"question": "Education", "answer": f"{edu.group(1)} {edu.group(2)}".strip()})
    langs = re.findall(r"^\|\s*([A-Z][a-z]+)\s*\|\s*([A-Z][a-z]+)\s*\|", text, re.M)
    if langs:
        out.append({"question": "Languages", "answer": ", ".join(f"{name} ({level})" for name, level in dict(langs).items())})
    primary = re.search(r"^\s*- \*\*Primary:\*\*\s*(.+?)\s*$", text, re.M)
    if primary:
        out.append({"question": "Main skills", "answer": primary.group(1)})
    return out


def checklist(item: dict, profile: str | None = None) -> dict:
    """What the user needs to submit by hand. No browser is opened and no form is filled."""
    out = {"title": item.get("title"), "company": item.get("company"), "type": item.get("type"), "apply_method": item.get("apply_method"),
           "link": item.get("apply_url") or item.get("url"), "cv_pdf": item.get("cv"), "screening_answers": screening_answers(profile),
           "not_in_profile": "Salary expectation, notice period, visa or work authorisation: answer these yourself."}
    if item.get("type") == "gig":
        out["proposal"] = item.get("proposal")
        out["connects_or_bids_cost"] = item.get("connects_or_bids_cost")
        out["after_sending"] = "python3 tools/freelance_guard.py record --gig-file <gig.json> --rate R --connects-spent N --user-confirmed yes"
    else:
        out["cover_letter_pdf"] = item.get("cover")
        out["after_sending"] = f"/outcome {item.get('company')} {item.get('title')} applied"
    return out


# ---------------------------------------------------------------- finish and report

def finish(run: dict, *, queue: Path = es.QUEUE, job_tracker: Path = sg.TRACKER, gig_tracker: Path = fg.TRACKER, today: date | None = None,
           profile: str | None = None) -> dict:
    """Give every prepared item its final status and write the trackers. A dry run writes no tracker."""
    today = today or date.today()
    data = es.load_queue(queue)
    if run.get("dry_run"):
        # A dry run's table must not carry over into a later approval; /submit re-queues these.
        for e in es.pending(data):
            e["status"] = "not_sent"
        sg.save_json(queue, data)
    emails = {e["id"]: e for e in data["items"]}
    for item in run["items"]:
        if item["status"] != "prepared":
            continue
        entry = emails.get(es.item_id(item)) if item.get("apply_method") == "email" else None
        if entry and entry["status"] in ("sent", "sending"):
            item["status"] = "emailed"
            item["message_id"] = entry.get("message_id")
            continue
        if entry and entry["status"] == "needs_review":
            item.update(status="needs_review", reason="; ".join(entry.get("reasons") or []))
            continue
        if entry and entry["status"] == "failed":
            item["reason"] = "; ".join(entry.get("reasons") or [])
        item["status"] = "ready_to_submit"
        item["checklist"] = checklist(item, profile)
        if run.get("dry_run"):
            continue
        note = f"{today.isoformat()} prepared by /autopilot - submit by hand"
        try:
            if item["type"] == "gig":
                fg.record(item, "", 0, None, tracker=gig_tracker, today=today, status="ready_to_submit", channel=item.get("apply_method") or "")
            else:
                sg.update_tracker(job_tracker, item.get("company") or "", item.get("title") or "", item.get("apply_method") or "", note, status="ready_to_submit")
        except sg.Refused as exc:
            item["warning"] = f"tracker not updated: {exc}"
    return run


def report(run: dict) -> dict:
    rows = {"scraped": dict(run.get("scraped") or {})}
    statuses = {"confirmed": ("selected", "prepared", "emailed", "ready_to_submit", "needs_review", "failed"), "emailed": ("emailed",),
                "ready_to_submit": ("ready_to_submit",), "needs_review": ("needs_review",), "failed": ("failed",)}
    counts = {t: {"scraped": rows["scraped"].get(t, 0)} for t in ("job", "gig")}
    for t in counts:
        for name, wanted in statuses.items():
            counts[t][name] = sum(1 for i in run["items"] if i["type"] == t and i["status"] in wanted)
    table = [{k: i.get(k) for k in ("id", "type", "company", "title", "idr_monthly_equiv", "fit_score", "apply_method", "status", "reason", "message_id", "warning")}
             for i in run["items"]]
    done = [i for i in run["items"] if i["status"] not in ("selected", "failed")]
    tokens = (TOKEN_ESTIMATE["scrape"] + TOKEN_ESTIMATE["rank_per_item"] * sum(rows["scraped"].values())
              + sum(TOKEN_ESTIMATE["apply" if i["type"] == "job" else "propose"] for i in done)
              + TOKEN_ESTIMATE["email"] * sum(1 for i in done if i["status"] == "emailed"))
    return {"dry_run": run.get("dry_run", False), "counts": counts, "table": table,
            "manual_checklists": [i["checklist"] for i in run["items"] if i.get("checklist")],
            "not_applied": {s: [{"type": r["type"], "title": r.get("title"), "reasons": r.get("reasons")} for r in v] for s, v in (run.get("listed") or {}).items()},
            "skipped": [{"type": r["type"], "title": r.get("title"), "reason": r.get("skip_reason")} for r in run.get("skipped") or []],
            "vetted_networks": run.get("vetted_networks") or [],
            "token_estimate": {"tokens": tokens, "note": "rough budget from fixed per-step figures, not a measurement"}}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Batch apply: selection, order, checklists, report")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("scope", "combine", "select"):
        s = sub.add_parser(name)
        s.add_argument("--jobs-only", action="store_true")
        s.add_argument("--gigs-only", action="store_true")
        if name == "combine":
            s.add_argument("--gigs", type=Path, help="tools/gig_rules.py evaluate output")
            s.add_argument("--seen", type=Path, default=sg.SEEN)
            s.add_argument("--out", type=Path)
        if name == "select":
            s.add_argument("--combined", type=Path, required=True)
            s.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
            s.add_argument("--max-items", type=int, default=MAX_ITEMS)
            s.add_argument("--min-fit", type=int, default=MIN_FIT)
            s.add_argument("--dry-run", action="store_true")
            s.add_argument("--out", type=Path, required=True)
    for name in ("next-item", "finish", "report"):
        sub.add_parser(name).add_argument("--run", type=Path, required=True)
    m = sub.add_parser("mark")
    m.add_argument("--run", type=Path, required=True)
    m.add_argument("--id", type=int, required=True)
    m.add_argument("--status", required=True)
    for flag in ("--reason", "--cv", "--cover", "--proposal", "--apply-method"):
        m.add_argument(flag)
    sub.add_parser("checklist").add_argument("--item", type=Path, required=True)
    args = p.parse_args(argv)

    def emit(obj) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    try:
        if args.cmd == "scope":
            emit(scope(only_flag(args.jobs_only, args.gigs_only)))
        elif args.cmd == "combine":
            gigs = sg.load_json(args.gigs, {}) if args.gigs else None
            out = combine(seen=args.seen, gigs=gigs, only=only_flag(args.jobs_only, args.gigs_only))
            if args.out:
                sg.save_json(args.out, out)
                emit({"saved": str(args.out), "counts": out["counts"], "scraped": out["scraped"]})
            else:
                emit(out)
        elif args.cmd == "select":
            out = select(sg.load_json(args.combined, {"sections": {}}), limit=args.limit, max_items=args.max_items, min_fit=args.min_fit,
                         only=only_flag(args.jobs_only, args.gigs_only), dry_run=args.dry_run)
            sg.save_json(args.out, out)
            emit({"saved": str(args.out), "selected": [{k: i.get(k) for k in ("id", "type", "company", "title", "idr_monthly_equiv", "apply_method")} for i in out["items"]],
                  "skipped": len(out["skipped"])})
        elif args.cmd == "next-item":
            emit(next_item(sg.load_json(args.run, {"items": []})))
        elif args.cmd == "mark":
            run = sg.load_json(args.run, {"items": []})
            item = mark(run, args.id, args.status, reason=args.reason, cv=args.cv, cover=args.cover, proposal=args.proposal, apply_method=args.apply_method)
            sg.save_json(args.run, run)
            emit({"id": item["id"], "status": item["status"]})
        elif args.cmd == "finish":
            run = finish(sg.load_json(args.run, {"items": []}))
            sg.save_json(args.run, run)
            emit(report(run))
        elif args.cmd == "report":
            emit(report(sg.load_json(args.run, {"items": []})))
        elif args.cmd == "checklist":
            emit(checklist(sg.load_json(args.item, {})))
    except sg.Refused as exc:
        print(json.dumps({"refused": str(exc), "code": "REFUSED"}, ensure_ascii=False), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
