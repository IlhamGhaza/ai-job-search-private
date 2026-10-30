"""tools/freelance_guard.py: humanizer detection, claim checks, duplicate guard, stop-before-send."""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools import freelance_guard as fg
from tools.fx_rates import FxTable

# freelance_guard imports submit_guard as a top-level module (tools/ on sys.path): use its class.
Refused = fg.Refused
TODAY = date(2026, 10, 30)
FX = FxTable(rates={"USD": 1 / 16000}, fetched_on="2026-10-30", source="test")
PROFILE = (
    "Mobile Developer (Contract) Quetra Asia Klandesin. Delivered five Flutter client apps. "
    "Primary: Flutter, Dart, BLoC, GetX, Provider, Clean Architecture. Secondary: Firebase (Auth, FCM), MQTT, SQLite. "
    "Converted 20+ Figma screens. GPA 3.72."
)
GIG_TEXT = "Fix crash in Flutter app with Firebase login. Budget 20 USD/hour. Riverpod preferred."


def gig(**over):
    base = {"platform": "Contra", "gig_id": "g1", "url": "https://contra.com/opportunity/g1", "title": "Fix Flutter crash",
            "client_verified_payment": True, "client_hires": 3, "client_rating": 5, "client_total_spent": 900,
            "budget_type": "hourly", "budget_min": 10, "budget_max": 20, "budget_currency": "USD", "est_duration": "1 week",
            "skills": ["Flutter"], "evidence": [], "source_type": "api", "connects_or_bids_cost": 0,
            "description": "Our Flutter app crashes on the Firebase login screen; fix it and add a test. " * 3}
    base.update(over)
    return base


class FakeRunner:
    def __init__(self, snapshot="form: proposal textarea e1, rate e2, send button e9"):
        self.calls = []
        self.snapshot = snapshot

    def __call__(self, args):
        self.calls.append(args)
        return self.snapshot if args[0] == "snapshot" else ""

    def clicked(self, ref):
        return ["click", ref] in self.calls


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.tracker = self.dir / "freelance_tracker.csv"
        self.proposal = self.dir / "proposal.txt"
        self.proposal.write_text("Hi, I build Flutter apps with Firebase Auth. I can fix the login crash this week.", encoding="utf-8")

    def plan(self, **gig_over):
        return {"gig": gig(**gig_over), "proposal_file": str(self.proposal), "rate": "20", "connects_or_bids_cost": 0, "send_ref": "e9",
                "fields": [{"label": "Cover letter", "ref": "e1", "value": self.proposal.read_text(encoding="utf-8"), "source": "proposal"},
                           {"label": "Hourly rate", "ref": "e2", "value": "20", "source": "rate"}]}


class HumanizerTests(Base):
    def test_missing_vs_present(self):
        missing = self.dir / "none.json"
        self.assertFalse(fg.humanizer_installed(missing))
        absent = self.dir / "other.json"
        absent.write_text(json.dumps({"plugins": {"caveman@caveman": [{}]}}), encoding="utf-8")
        self.assertFalse(fg.humanizer_installed(absent))
        present = self.dir / "installed.json"
        present.write_text(json.dumps({"plugins": {"humanizer@humanizer": [{"version": "3.1.0"}]}}), encoding="utf-8")
        self.assertTrue(fg.humanizer_installed(present))

    def test_cli_reports_status(self):
        present = self.dir / "installed.json"
        present.write_text(json.dumps({"plugins": {"humanizer@humanizer": [{}]}}), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fg.main(["humanizer-status", "--plugins-file", str(present)]), 0)
        self.assertTrue(json.loads(out.getvalue())["installed"])

    def test_humanizer_adding_a_claim_is_flagged(self):
        draft = "I build Flutter apps with Firebase Auth and can fix the crash."
        added = "I've shipped 30 Flutter apps with Firebase and Riverpod, and I'm Top Rated with 50 reviews."
        problems = fg.humanizer_check(draft, added, GIG_TEXT, [], PROFILE)
        joined = " | ".join(problems)
        for needle in ("'30'", "'riverpod'", "Top Rated", "50 reviews"):
            self.assertIn(needle, joined)

    def test_faithful_humanizer_output_passes(self):
        draft = "I build Flutter apps with Firebase Auth and can fix the crash."
        human = "I build apps in Flutter and Firebase Auth, and I can sort out this crash."
        self.assertEqual(fg.humanizer_check(draft, human, GIG_TEXT, [], PROFILE), [])


class ClaimsTests(Base):
    def test_profile_and_gig_values_pass_unknown_values_flag(self):
        self.assertEqual(fg.claims_check("I delivered five Flutter client apps with BLoC.", GIG_TEXT, [], PROFILE), [])
        problems = fg.claims_check("I have 4 years of Swift experience.", GIG_TEXT, [], PROFILE)
        self.assertTrue(any("'4'" in p for p in problems))
        self.assertTrue(any("'swift'" in p for p in problems))

    def test_user_given_rate_is_allowed(self):
        self.assertEqual(fg.claims_check("My rate is 18 USD/hour.", GIG_TEXT, ["18 USD/hour"], PROFILE), [])


class CheckTests(Base):
    def test_duplicate_proposal_and_daily_limit(self):
        self.assertTrue(fg.check(gig(), tracker=self.tracker, today=TODAY, fx=FX)["allowed"])
        fg.record(gig(), "20", 0, None, tracker=self.tracker, today=TODAY)
        out = fg.check(gig(), tracker=self.tracker, today=TODAY, fx=FX)
        self.assertFalse(out["allowed"])
        self.assertIn("never propose twice", " ".join(out["reasons"]))
        for i in range(2, 6):
            fg.record(gig(gig_id=f"g{i}", url=f"https://contra.com/opportunity/g{i}"), "20", 0, None, tracker=self.tracker, today=TODAY)
        limited = fg.check(gig(gig_id="g9", url="https://contra.com/opportunity/g9"), tracker=self.tracker, today=TODAY, fx=FX)
        self.assertIn("daily limit", " ".join(limited["reasons"]))
        with self.assertRaises(Refused):
            fg.record(gig(), "20", 0, None, tracker=self.tracker, today=TODAY)

    def test_rejected_and_unreviewed_gigs_are_refused(self):
        self.assertFalse(fg.check(gig(client_country="Cambodia"), tracker=self.tracker, today=TODAY, fx=FX)["allowed"])
        risky = gig(client_verified_payment=False)
        self.assertFalse(fg.check(risky, tracker=self.tracker, today=TODAY, fx=FX)["allowed"])
        self.assertTrue(fg.check(risky, safety_reviewed=True, tracker=self.tracker, today=TODAY, fx=FX)["allowed"])

    def test_upwork_and_freelancer_are_fill_only(self):
        out = fg.check(gig(platform="Upwork", url="https://www.upwork.com/jobs/~01"), tracker=self.tracker, today=TODAY, fx=FX)
        self.assertTrue(out["fill_only_forced"])
        self.assertEqual(out["mode_default"], "fill_only")
        self.assertTrue(fg.fill_only_forced("https://www.freelancer.co.id/projects/x"))
        self.assertFalse(fg.fill_only_forced("https://contra.com/opportunity/1"))

    def test_tracker_has_the_agreed_columns(self):
        fg.record(gig(), "20", 0, str(self.dir / "s.png"), tracker=self.tracker, today=TODAY)
        with self.tracker.open(encoding="utf-8") as fh:
            row = next(csv.DictReader(fh))
        self.assertEqual(list(row), fg.TRACKER_FIELDS)
        self.assertEqual((row["platform"], row["status"], row["date"]), ("Contra", "proposed", "2026-10-30"))


class StopBeforeSendTests(Base):
    def test_fill_never_clicks_send(self):
        runner = FakeRunner()
        out = fg.fill(self.plan(), runner, tracker=self.tracker, shots=self.dir, today=TODAY)
        self.assertEqual(out["status"], "filled_waiting_for_user")
        self.assertFalse(runner.clicked("e9"))
        self.assertTrue(any(c[0] == "screenshot" for c in runner.calls))
        self.assertFalse(self.tracker.exists())

    def test_fill_pauses_on_login_or_captcha(self):
        with self.assertRaises(Refused):
            fg.fill(self.plan(), FakeRunner("Please verify you are human (CAPTCHA)"), tracker=self.tracker, shots=self.dir, today=TODAY)

    def test_fill_refuses_edited_text_unconfirmed_fields_and_id_fields(self):
        for mutate in (
            lambda p: p["fields"][0].update(value="I have 10 years of experience."),
            lambda p: p["fields"].append({"label": "Portfolio", "ref": "e3", "value": "https://x.test"}),
            lambda p: p["fields"].append({"label": "Passport number", "ref": "e4", "value": "A1", "user_confirmed": True}),
            lambda p: p["fields"][1].update(value="25"),
        ):
            plan = self.plan()
            mutate(plan)
            with self.subTest(plan=plan["fields"][-1]["label"]), self.assertRaises(Refused):
                fg.fill(plan, FakeRunner(), tracker=self.tracker, shots=self.dir, today=TODAY)

    def test_send_refused_for_upwork_without_yes_with_changed_plan_or_unapproved_spend(self):
        up = self.plan(platform="Upwork", url="https://www.upwork.com/jobs/~01")
        runner = FakeRunner()
        with self.assertRaises(Refused):
            fg.send(up, runner, confirm="yes", given_hash=fg.review_hash(up), mode="confirm_then_click", approve_spend="0",
                    tracker=self.tracker, shots=self.dir, today=TODAY)
        plan = self.plan()
        h = fg.review_hash(plan)
        for kw in ({"confirm": "ok", "given_hash": h, "mode": "confirm_then_click", "approve_spend": "0"},
                   {"confirm": "yes", "given_hash": "other", "mode": "confirm_then_click", "approve_spend": "0"},
                   {"confirm": "yes", "given_hash": h, "mode": "fill_only", "approve_spend": "0"}):
            with self.subTest(kw=kw), self.assertRaises(Refused):
                fg.send(plan, runner, tracker=self.tracker, shots=self.dir, today=TODAY, **kw)
        costly = self.plan()
        costly["connects_or_bids_cost"] = 4
        with self.assertRaises(Refused):
            fg.send(costly, runner, confirm="yes", given_hash=fg.review_hash(costly), mode="confirm_then_click", approve_spend=None,
                    tracker=self.tracker, shots=self.dir, today=TODAY)
        self.assertFalse(runner.clicked("e9"))

    def test_send_after_yes_clicks_once_records_and_blocks_a_second_send(self):
        plan = self.plan()
        runner = FakeRunner()
        out = fg.send(plan, runner, confirm="yes", given_hash=fg.review_hash(plan), mode="confirm_then_click", approve_spend="0",
                      tracker=self.tracker, shots=self.dir, today=TODAY)
        self.assertEqual(out["status"], "recorded")
        self.assertTrue(runner.clicked("e9"))
        with self.assertRaises(Refused):
            fg.send(plan, FakeRunner(), confirm="yes", given_hash=fg.review_hash(plan), mode="confirm_then_click", approve_spend="0",
                    tracker=self.tracker, shots=self.dir, today=TODAY)


class EmailTests(Base):
    def test_address_must_come_from_the_gig(self):
        g = gig(description="Flutter fix. Send proposals to hiring@client.example. " * 2)
        out = fg.email_draft(g, "hiring@client.example", "Flutter fix", "Hello", self.dir / "d.eml")
        self.assertEqual(out["status"], "draft_saved")
        self.assertIn(b"X-Unsent: 1", (self.dir / "d.eml").read_bytes())
        with self.assertRaises(Refused):
            fg.email_draft(g, "other@evil.example", "x", "y", self.dir / "e.eml")


if __name__ == "__main__":
    unittest.main()
