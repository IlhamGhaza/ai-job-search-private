"""/submit guards (tools/submit_guard.py): preconditions, duplicate guard,
tracker recording, email drafts. No live site, no real tracker.
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
