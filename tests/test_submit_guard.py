"""/submit guards (tools/submit_guard.py): preconditions, stop-before-submit,
duplicate guard, tracker recording, email drafts.

A fake Playwright runner stands in for the browser: it records every command
and serves canned snapshots. No live site, no real tracker.
"""

import email
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import submit_guard as sg  # noqa: E402

PROFILE = """- **Name:** Muhammad Ilham Ghazali
- **Location:** Bogor, Indonesia (remote-first)
- **Status:** Available immediately
"""
HEADER = "date,company,sector,role,role_type,channel,status,contact_person,fit_rating,notes,cv_file,cover_letter_file,source,deadline"


class FakePage:
    """Records playwright-cli commands; `snapshot` returns `page_text`."""

    def __init__(self, page_text="<form>Apply for Junior Flutter Developer</form>"):
        self.page_text = page_text
        self.commands: list[list[str]] = []

    def __call__(self, args):
        self.commands.append(list(args))
        return self.page_text if args[0] == "snapshot" else "ok"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.cv = self.dir / "main_acme_flutter.tex"
        self.cover = self.dir / "cover_acme_flutter.tex"
        for f in (self.cv, self.cover):
            f.write_text("x", encoding="utf-8")
            f.with_suffix(".pdf").write_bytes(b"%PDF-1.4 test")
        self.tracker = self.dir / "tracker.csv"
        self.tracker.write_text(
            HEADER + "\n"
            + f"2026-10-30,Acme,,Junior Flutter Developer,,,drafted,,80,drafted by /apply,{self.cv},{self.cover},https://boards.greenhouse.io/acme/jobs/1,\n"
            + "2026-10-29,Other,,Dev,,online,applied,,,untouched row,,,https://x.example/1,\n",
            encoding="utf-8",
        )
        self.ledger = self.dir / "submissions.json"
        self.seen = self.dir / "seen.json"
        self.job = {
            "title": "Junior Flutter Developer", "company": "Acme", "location": "Jakarta, Indonesia", "country": "ID",
            "url": "https://boards.greenhouse.io/acme/jobs/1", "portal": "ats-search", "employment_type": "Full-time",
            "description": "Flutter, 1 year experience.", "date": "2026-10-28", "salary_min": 9_000_000, "salary_max": None,
            "salary_currency": "IDR", "salary_period": "month", "evidence": ["Greenhouse job board API"],
        }
        self.seen.write_text(json.dumps({"seen": {"acme-key": self.job}}), encoding="utf-8")
        self.shots = self.dir / "shots"

    def check(self, **kw):
        return sg.check("Acme", "Junior Flutter Developer", key="acme-key", tracker=self.tracker, seen_path=self.seen,
                        ledger=self.ledger, today=date(2026, 10, 30), fx_cache=self.dir / "nofx.json", **kw)

    def plan(self, **kw):
        p = {
            "job": {"company": "Acme", "role": "Junior Flutter Developer", "url": "https://boards.greenhouse.io/acme/jobs/1"},
            "cv_pdf": str(self.cv.with_suffix(".pdf")), "cover_pdf": str(self.cover.with_suffix(".pdf")),
            "fields": [
                {"label": "Full name", "ref": "e1", "value": "Muhammad Ilham Ghazali", "source_quote": "**Name:** Muhammad Ilham Ghazali"},
                {"label": "Resume", "ref": "e2", "kind": "upload", "value": str(self.cv.with_suffix(".pdf"))},
            ],
            "submit_ref": "e9",
            "channel": "ats_form",
        }
        p.update(kw)
        return p


class CheckTests(Fixture):
    def test_allowed_when_everything_holds(self):
        r = self.check()
        self.assertTrue(r["allowed"], r["reasons"])
        self.assertEqual(r["apply_method"], "ats_form")
        self.assertEqual(r["mode_default"], "confirm_then_click")

    def test_refused_without_apply_artifacts(self):
        self.cv.with_suffix(".pdf").unlink()
        r = self.check()
        self.assertFalse(r["allowed"])
        self.assertTrue(any("PDF" in x for x in r["reasons"]))

    def test_refused_when_safety_not_verified(self):
        self.job["portal"] = "jobsites-search"
        self.seen.write_text(json.dumps({"seen": {"acme-key": self.job}}), encoding="utf-8")
        r = self.check()
        self.assertFalse(r["allowed"])
        self.assertTrue(any("safety_screening" in x for x in r["reasons"]))

    def test_refused_when_hard_rules_fail(self):
        self.job["salary_min"] = 5_000_000
        self.seen.write_text(json.dumps({"seen": {"acme-key": self.job}}), encoding="utf-8")
        r = self.check()
        self.assertFalse(r["allowed"])
        self.assertTrue(any("rejected" in x for x in r["reasons"]))

    def test_refused_when_already_applied(self):
        self.tracker.write_text(self.tracker.read_text(encoding="utf-8").replace(",drafted,", ",applied,"), encoding="utf-8")
        self.assertFalse(self.check()["allowed"])

    def test_daily_limit_per_portal(self):
        now = "2026-10-30T09:00:00+00:00"
        self.ledger.write_text(json.dumps({"submissions": [{"company": f"C{i}", "role": "R", "url": f"https://boards.greenhouse.io/c{i}/jobs/1", "portal": "greenhouse.io", "submitted_at": now} for i in range(10)]}), encoding="utf-8")
        r = self.check()
        self.assertFalse(r["allowed"])
        self.assertTrue(any("daily limit" in x for x in r["reasons"]))

    def test_portal_login_defaults_to_fill_only_with_tos_warning(self):
        self.job["url"] = "https://www.linkedin.com/jobs/view/1"
        self.seen.write_text(json.dumps({"seen": {"acme-key": self.job}}), encoding="utf-8")
        r = self.check()
        self.assertEqual(r["mode_default"], "fill_only")
        self.assertTrue(any("Terms" in w for w in r["warnings"]))


class FillAndSubmitTests(Fixture):
    def test_fill_stops_before_submit(self):
        page = FakePage()
        out = sg.fill(self.plan(), page, screenshots=self.shots, profile=PROFILE)
        self.assertEqual(out["status"], "filled_waiting_for_user")
        self.assertNotIn(["click", "e9"], page.commands)
        self.assertTrue(any(c[0] == "screenshot" for c in page.commands))
        self.assertIn(["fill", "e1", "Muhammad Ilham Ghazali"], page.commands)
        upload = next(c for c in page.commands if c[0] == "upload")
        self.assertTrue(Path(upload[1]).is_absolute())

    def test_invented_or_missing_answers_stop_the_fill(self):
        plan = self.plan(fields=[{"label": "Years of Flutter experience", "ref": "e3", "value": "5", "source_quote": "I have 5 years"}])
        with self.assertRaises(sg.Refused):
            sg.fill(plan, FakePage(), screenshots=self.shots, profile=PROFILE)
        plan = self.plan(fields=[{"label": "Expected salary", "ref": "e4", "value": None}])
        with self.assertRaisesRegex(sg.Refused, "ASK USER"):
            sg.fill(plan, FakePage(), screenshots=self.shots, profile=PROFILE)

    def test_payment_or_passport_fields_flag_a_scam(self):
        plan = self.plan(fields=[{"label": "Passport scan", "ref": "e5", "kind": "upload", "value": str(self.cv.with_suffix(".pdf"))}])
        with self.assertRaisesRegex(sg.Refused, "scam"):
            sg.fill(plan, FakePage(), screenshots=self.shots, profile=PROFILE)

    def test_only_the_two_pdfs_may_be_uploaded(self):
        other = self.dir / "id.pdf"
        other.write_bytes(b"%PDF")
        plan = self.plan(fields=[{"label": "Attachment", "ref": "e6", "kind": "upload", "value": str(other)}])
        with self.assertRaises(sg.Refused):
            sg.fill(plan, FakePage(), screenshots=self.shots, profile=PROFILE)

    def test_login_or_captcha_pauses(self):
        with self.assertRaisesRegex(sg.Refused, "PAUSE"):
            sg.fill(self.plan(), FakePage("Please verify you are human (CAPTCHA)"), screenshots=self.shots, profile=PROFILE)

    def test_submit_requires_explicit_yes_and_unchanged_plan(self):
        plan = self.plan()
        h = sg.fill(plan, FakePage(), screenshots=self.shots, profile=PROFILE)["review_hash"]
        page = FakePage()
        for confirm, given in (("y", h), ("ok", h), ("yes", "0" * 16)):
            with self.assertRaises(sg.Refused):
                sg.submit(plan, page, confirm=confirm, given_hash=given, mode="confirm_then_click", ledger=self.ledger, tracker=self.tracker, screenshots=self.shots)
        self.assertEqual(page.commands, [], "nothing may be clicked without an explicit yes on the reviewed plan")
        changed = self.plan(fields=plan["fields"] + [{"label": "Note", "ref": "e7", "value": "Bogor, Indonesia", "source_quote": "Bogor, Indonesia"}])
        with self.assertRaisesRegex(sg.Refused, "changed"):
            sg.submit(changed, page, confirm="yes", given_hash=h, mode="confirm_then_click", ledger=self.ledger, tracker=self.tracker, screenshots=self.shots)

    def test_fill_only_mode_never_clicks(self):
        plan = self.plan()
        h = sg.review_hash(plan)
        page = FakePage()
        with self.assertRaisesRegex(sg.Refused, "fill-only"):
            sg.submit(plan, page, confirm="yes", given_hash=h, mode="fill_only", ledger=self.ledger, tracker=self.tracker, screenshots=self.shots)
        self.assertEqual(page.commands, [])

    def test_yes_clicks_once_records_and_blocks_a_second_submit(self):
        plan = self.plan()
        h = sg.review_hash(plan)
        page = FakePage()
        before_other = self.tracker.read_text(encoding="utf-8").splitlines()[2]
        out = sg.submit(plan, page, confirm="yes", given_hash=h, mode="confirm_then_click", ledger=self.ledger, tracker=self.tracker,
                        screenshots=self.shots, now=datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(out["status"], "recorded")
        self.assertEqual(page.commands[0], ["click", "e9"])
        lines = self.tracker.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], HEADER)
        self.assertIn(",applied,", lines[1])
        self.assertIn("2026-10-30 submitted via ats_form", lines[1])
        self.assertTrue(lines[1].endswith("https://boards.greenhouse.io/acme/jobs/1,"))
        self.assertEqual(lines[2], before_other, "other rows are never touched")
        with self.assertRaisesRegex(sg.Refused, "already submitted"):
            sg.submit(plan, FakePage(), confirm="yes", given_hash=h, mode="confirm_then_click", ledger=self.ledger, tracker=self.tracker, screenshots=self.shots)
        self.assertFalse(self.check()["allowed"])


class LoginTests(unittest.TestCase):
    def test_login_opens_headed_persistent_profile_and_types_nothing(self):
        page = FakePage()
        out = sg.login(page, "www.LinkedIn.com")
        self.assertEqual(out["portal"], "linkedin.com")
        cmd = page.commands[0]
        self.assertEqual(cmd[:2], ["open", "https://www.linkedin.com/login"])
        self.assertIn("--headed", cmd)
        self.assertIn("--persistent", cmd)
        self.assertTrue(any(c.startswith("--profile=") and ".browser-profile" in c for c in cmd))
        self.assertEqual(len(page.commands), 1, "login only opens the window: no fill, no type, no state-save")

    def test_unknown_portal_opens_its_home_page_and_bad_input_is_refused(self):
        page = FakePage()
        self.assertEqual(sg.login(page, "powertofly.com")["url"], "https://powertofly.com/")
        with self.assertRaises(sg.Refused):
            sg.login(FakePage(), "javascript:alert(1)")


class EmailDraftTests(Fixture):
    def test_draft_has_subject_body_and_both_pdfs(self):
        out_path = self.dir / "draft.eml"
        r = sg.email_draft("Junior Flutter Developer", "hr@acme.example", "Send your CV to hr@acme.example", "Dear Hiring Manager,\nI am applying.",
                           self.cv.with_suffix(".pdf"), self.cover.with_suffix(".pdf"), None, out_path)
        self.assertEqual(r["status"], "draft_saved")
        msg = email.message_from_bytes(out_path.read_bytes())
        self.assertIn("Junior Flutter Developer", msg["Subject"])
        self.assertEqual(msg["To"], "hr@acme.example")
        names = [part.get_filename() for part in msg.walk() if part.get_filename()]
        self.assertEqual(names, ["main_acme_flutter.pdf", "cover_acme_flutter.pdf"])

    def test_address_must_come_from_the_posting(self):
        with self.assertRaises(sg.Refused):
            sg.email_draft("T", "attacker@evil.example", "Send your CV to hr@acme.example", "body",
                           self.cv.with_suffix(".pdf"), self.cover.with_suffix(".pdf"), None, self.dir / "x.eml")


class RealTrackerUntouchedTests(unittest.TestCase):
    def test_check_is_read_only_on_the_real_tracker(self):
        tracker = ROOT / "job_search_tracker.csv"
        if not tracker.is_file():
            self.skipTest("no tracker in this checkout")
        before = hashlib.sha256(tracker.read_bytes()).hexdigest()
        sg.check("No Such Company Zzz", "No Role", key="none", ledger=Path(tempfile.mkdtemp()) / "l.json")
        self.assertEqual(before, hashlib.sha256(tracker.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
