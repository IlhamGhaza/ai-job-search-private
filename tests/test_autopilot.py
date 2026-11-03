"""tools/autopilot.py and the merged /scrape + /rank view: scope, sort key, selection, batch, final statuses."""

import json
import re
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from tools import autopilot as ap
from tools.fx_rates import FxTable
from tools.gig_rules import evaluate

es = ap.es
fg = ap.fg
sg = ap.sg
ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 10, 31)
FX = FxTable(rates={"USD": 1 / 16000, "EUR": 1 / 17500}, fetched_on="2026-10-31", source="test")
PROFILE = "- **Name:** Muhammad Ilham Ghazali\n- **Email:** a@b.example\n- **Status:** Available immediately\n- **Primary:** Flutter, Dart\n"


def gig(**over):
    base = {"type": "gig", "platform": "Upwork", "gig_id": "100", "url": "https://www.upwork.com/jobs/~01100", "title": "Fix bugs in Flutter app",
            "client_country": "Germany", "client_verified_payment": True, "client_rating": 4.8, "client_hires": 5, "client_total_spent": 2500,
            "budget_type": "hourly", "budget_min": 10, "budget_max": 20, "budget_currency": "USD", "est_duration": "1 to 3 months", "skills": ["Flutter"],
            "proposals_count": 8, "posted_at": "2026-10-29", "apply_method": "platform_proposal", "evidence": [], "source_type": "api",
            "description": "Our Flutter app crashes on the Firebase login screen. Fix the crash and add tests. " * 3}
    base.update(over)
    return base


def row(kind="job", section="confirmed", safety="verified_low_concern", idr=10_000_000, fit=70, title="Flutter Dev", **over):
    base = {"type": kind, "title": title, "company": over.pop("company", f"{title} Co"), "url": over.pop("url", f"https://x.test/{title.replace(' ', '-')}"), "section": section, "reasons": [],
            "safety_screening": safety, "apply_method": "ats_form", "idr_monthly_equiv": idr, "fit_score": fit, "posted_date": "2026-10-29"}
    if kind == "gig":
        base.update(platform="Upwork", gig_id=title, apply_method="platform_proposal")
    base.update(over)
    return base


def combined(*rows):
    return {"sections": {s: [r for r in rows if r["section"] == s] for s in ap.SECTIONS}, "scraped": {"job": 1, "gig": 1}, "vetted_networks": [{"name": "Arc.dev"}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.jobs = self.dir / "job_search_tracker.csv"
        self.gigs = self.dir / "freelance_tracker.csv"
        self.queue = self.dir / "queue.json"
        self.ledger = self.dir / "submissions.json"
        self.jobs.write_text("date,company,role,channel,status,notes,source\n", encoding="utf-8")

    def select(self, *rows, **kw):
        return ap.select(combined(*rows), job_tracker=self.jobs, gig_tracker=self.gigs, ledger=self.ledger, queue=self.queue, today=TODAY, **kw)


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.skills = Path(tempfile.mkdtemp())
        for name, fm in (("jobx-search", "enabled: true"), ("offjob-search", "enabled: false"), ("gigx-search", "category: freelance\nenabled: true"),
                         ("offgig-search", "category: freelance\nenabled: false"), ("nokey-search", "name: x")):
            (self.skills / name / "cli").mkdir(parents=True)
            (self.skills / name / "SKILL.md").write_text(f"---\n{fm}\n---\n\nenabled: false in the body means nothing\n", encoding="utf-8")
        (self.skills / "design-skill").mkdir()  # no cli/: not a portal
        (self.skills / "design-skill" / "SKILL.md").write_text("---\nname: design-skill\n---\n", encoding="utf-8")

    def test_default_runs_both_types(self):
        s = ap.scope(None, self.skills)
        self.assertEqual(s["types"], ["job", "gig"])
        self.assertEqual(s["job_skills"], ["jobx-search", "nokey-search"])
        self.assertEqual(s["gig_skills"], ["gigx-search"])
        self.assertEqual(sorted(s["skipped_disabled"]), ["offgig-search", "offjob-search"])

    def test_jobs_only_and_gigs_only(self):
        self.assertEqual(ap.scope("job", self.skills)["gig_skills"], [])
        self.assertEqual(ap.scope("gig", self.skills)["job_skills"], [])
        self.assertEqual(ap.scope("gig", self.skills)["types"], ["gig"])

    def test_both_flags_refused(self):
        with self.assertRaises(sg.Refused):
            ap.only_flag(True, True)

    def test_real_tree_splits_jobs_and_gigs(self):
        s = ap.scope()
        self.assertIn("upwork-search", s["gig_skills"])
        self.assertIn("remotive-search", s["job_skills"])
        self.assertNotIn("upwork-search", s["job_skills"])
        self.assertNotIn("frontend-design", s["job_skills"] + s["skipped_disabled"])

    def test_gigs_alias_and_scrape_flags_are_documented(self):
        gigs = (ROOT / ".claude" / "commands" / "gigs.md").read_text(encoding="utf-8")
        scrape = (ROOT / ".claude" / "skills" / "job-scraper" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("alias for `/scrape --gigs-only`", gigs)
        self.assertIn("scope --gigs-only", gigs)
        for needle in ("--jobs-only", "--gigs-only", "tools/autopilot.py scope", "Step 4.6"):
            self.assertIn(needle, scrape)


class SortKeyTests(unittest.TestCase):
    def equiv(self, **over):
        return evaluate([gig(**over)], FX, TODAY, tracker=None)

    def rule(self, **over):
        out = self.equiv(**over)
        rows = [g for v in out["sections"].values() for g in v]
        return rows[0]["rules"]["idr_monthly_equiv"]

    def test_job_uses_its_salary_floor_field(self):
        r = ap.job_row("k", {"title": "T", "company": "C", "url": "u", "rules_section": "confirmed", "salary_idr_monthly_min": 12_000_000})
        self.assertEqual((r["type"], r["idr_monthly_equiv"]), ("job", 12_000_000))

    def test_hourly_gig_is_rate_times_173(self):
        self.assertEqual(self.rule(budget_min=10), 160_000 * 173)

    def test_fixed_gig_with_duration_divides_by_months(self):
        self.assertEqual(self.rule(budget_type="fixed", budget_min=1000, budget_max=1000, est_duration="1 to 2 months"), 8_000_000)

    def test_fixed_gig_shorter_than_a_month_counts_as_one_month(self):
        self.assertEqual(self.rule(budget_type="fixed", budget_min=1000, budget_max=1000, est_duration="3 days"), 16_000_000)

    def test_fixed_gig_without_duration_is_null_and_needs_budget_review(self):
        out = self.equiv(budget_type="fixed", budget_min=1000, budget_max=1000, est_duration=None)
        g = out["sections"]["needs_budget_client_review"][0]
        self.assertIsNone(g["rules"]["idr_monthly_equiv"])
        r = ap.gig_row(g)
        self.assertEqual(r["section"], "needs_verification")
        self.assertTrue(r["needs_budget_review"])

    def test_records_carry_their_type(self):
        self.assertEqual(self.equiv()["sections"]["good_fits"][0]["type"], "gig")
        from tools.job_rules import evaluate as evaluate_jobs

        out = evaluate_jobs([{"title": "Junior Flutter Developer", "company": "A", "url": "https://x.test/1"}], FX, TODAY)
        self.assertEqual(next(r for v in out["sections"].values() for r in v)["type"], "job")


class CombineTests(Base):
    def test_one_list_with_a_type_and_dedup_within_gigs(self):
        seen = self.dir / "seen.json"
        seen.write_text(json.dumps({"seen": {
            "a": {"title": "Job A", "company": "A", "url": "https://x.test/a", "status": "ranked", "rules_section": "confirmed", "salary_idr_monthly_min": 9_000_000,
                  "safety_screening": "verified_low_concern", "rank_score": 80, "apply_method": "email", "apply_email": "hr@a.io"},
            "old": {"title": "Old", "status": "skipped", "first_seen": "2020-01-01", "rules_section": "rejected"},
            "exp": {"title": "Expired", "status": "expired", "first_seen": "2026-10-31", "rules_section": "confirmed"},
            "veto": {"title": "Veto", "status": "ranked", "rules_section": "confirmed", "language_gate": "FAIL", "language_note": "needs Polish"},
        }}), encoding="utf-8")
        gigs = evaluate([gig(), gig()], FX, TODAY, tracker=None)
        self.assertEqual(gigs["duplicates_dropped"], 1)
        out = ap.combine(seen=seen, gigs=gigs, since="2026-10-31")
        confirmed = out["sections"]["confirmed"]
        self.assertEqual([r["type"] for r in confirmed], ["gig", "job"])
        self.assertEqual(confirmed[1]["to"], "hr@a.io")
        titles = [r["title"] for v in out["sections"].values() for r in v]
        self.assertNotIn("Old", titles)
        self.assertNotIn("Expired", titles)
        self.assertEqual(out["sections"]["rejected"][0]["title"], "Veto")
        self.assertTrue(out["vetted_networks"])

    def test_only_flags(self):
        seen = self.dir / "seen.json"
        seen.write_text(json.dumps({"seen": {"a": {"title": "Job", "status": "ranked", "rules_section": "confirmed"}}}), encoding="utf-8")
        gigs = evaluate([gig()], FX, TODAY, tracker=None)
        self.assertEqual(ap.combine(seen=seen, gigs=gigs, only="job")["scraped"], {"job": 1, "gig": 0})
        self.assertEqual(ap.combine(seen=seen, gigs=gigs, only="gig")["scraped"], {"job": 0, "gig": 1})

    def test_rank_documents_the_type_column_and_merge(self):
        rank = (ROOT / ".claude" / "commands" / "rank.md").read_text(encoding="utf-8")
        for needle in ("| # | Type |", "autopilot.py combine", "Vetted networks to apply to once", "--gigs-only"):
            self.assertIn(needle, rank)


class SelectTests(Base):
    def test_only_confirmed_and_verified(self):
        out = self.select(row(title="Good"), row(title="Pending", safety="verification_pending"), row(title="NV", section="needs_verification"),
                          row(title="Risk", section="manual_safety_review"), row(title="Bad", section="rejected"))
        self.assertEqual([i["title"] for i in out["items"]], ["Good"])
        self.assertEqual([r["title"] for r in out["skipped"]], ["Pending"])
        self.assertEqual({k: len(v) for k, v in out["listed"].items()}, {"needs_verification": 1, "manual_safety_review": 1, "rejected": 1})

    def test_fit_sort_puts_the_highest_fit_first_with_pay_breaking_ties(self):
        out = self.select(row(title="Low job", idr=6_000_000), row("gig", title="High gig", idr=30_000_000), row(title="Mid job", idr=15_000_000),
                          row("gig", title="Top fit gig", idr=7_000_000, fit=90), sort="fit")
        self.assertEqual([i["title"] for i in out["items"]], ["Top fit gig", "High gig", "Mid job", "Low job"])
        self.assertEqual([i["id"] for i in out["items"]], [1, 2, 3, 4])

    def test_inside_a_fit_band_eligibility_then_freshness_decide(self):
        out = self.select(row(title="Paid more", idr=30_000_000, fit=74, posted_date="2026-10-20"),
                          row(title="Newest", idr=8_000_000, fit=71, posted_date="2026-10-30"),
                          row(title="Needs visa", idr=40_000_000, fit=79, posted_date="2026-10-30", eligibility="visa_evidence"), sort="fit")
        self.assertEqual([i["title"] for i in out["items"]], ["Newest", "Paid more", "Needs visa"])

    def test_default_sort_puts_disclosed_pay_first_then_estimates_by_median(self):
        est = {"idr": None, "salary_source": "estimated"}
        out = self.select(row(title="Disclosed low", idr=6_000_000), row(title="Est A", salary_tier="A", benchmark_median_idr=60_000_000, **est),
                          row(title="Disclosed high", idr=20_000_000), row(title="Est B", salary_tier="B", benchmark_median_idr=7_000_000, **est),
                          row("gig", title="Gig", idr=9_000_000))
        self.assertEqual([i["title"] for i in out["items"]], ["Disclosed high", "Gig", "Disclosed low", "Est A", "Est B"])
        self.assertEqual([i.get("salary_source") for i in out["items"]][-2:], ["estimated", "estimated"])

    def test_estimated_tier_c_or_unknown_pay_is_never_selected(self):
        est = {"idr": None, "salary_source": "estimated"}
        out = self.select(row(title="Tier C", salary_tier="C", benchmark_median_idr=6_000_000, **est), row(title="No pay", idr=None),
                          row(title="Tier B", salary_tier="B", benchmark_median_idr=7_000_000, **est))
        self.assertEqual([i["title"] for i in out["items"]], ["Tier B"])
        self.assertEqual({r["title"] for r in out["skipped"]}, {"Tier C", "No pay"})

    def test_estimated_jobs_count_against_the_same_limit(self):
        est = {"idr": None, "salary_source": "estimated", "salary_tier": "A", "benchmark_median_idr": 50_000_000}
        out = self.select(row(title="D1", idr=8_000_000), row(title="E1", **est), row(title="E2", **est), limit=2)
        self.assertEqual([i["title"] for i in out["items"]], ["D1", "E1"])

    def test_checklist_never_fills_an_expected_salary(self):
        suggestion = {"amount": 7_000_000, "currency": "IDR", "period": "month", "needs_confirmation": True}
        c = ap.checklist({"type": "job", "title": "T", "company": "C", "salary_source": "estimated", "expected_salary_suggestion": suggestion})
        self.assertEqual((c["expected_salary"]["status"], c["expected_salary"]["value_to_use"]), ("needs_user_confirmation", None))
        self.assertEqual(c["expected_salary"]["amount"], 7_000_000)
        self.assertEqual(c["salary_source"], "estimated")

    def test_fit_below_the_default_line_is_skipped(self):
        self.assertEqual(ap.MIN_FIT, 60)
        out = self.select(row(title="Moderate", fit=59), row(title="Strong", fit=60))
        self.assertEqual([i["title"] for i in out["items"]], ["Strong"])

    def test_different_currencies_sort_on_the_idr_value(self):
        gigs = evaluate([gig(gig_id="usd", url="https://x.test/usd", budget_min=10), gig(gig_id="eur", url="https://x.test/eur", budget_min=10, budget_currency="EUR"),
                         gig(gig_id="idr", url="https://x.test/idr", budget_min=100_000, budget_currency="IDR")], FX, TODAY, tracker=None)
        out = ap.select(ap.combine(seen=self.dir / "none.json", gigs=gigs), job_tracker=self.jobs, gig_tracker=self.gigs, ledger=self.ledger, queue=self.queue, today=TODAY)
        self.assertEqual([i["gig_id"] for i in out["items"]], ["eur", "usd", "idr"])

    def test_already_tracked_is_excluded_per_type(self):
        self.jobs.write_text("date,company,role,channel,status,notes,source\n2026-10-30,Done Co,Done,,applied,,\n2026-10-30,X,Y,,drafted,,https://x.test/by-url\n", encoding="utf-8")
        fg.record({"title": "G", "platform": "Upwork", "gig_id": "sent", "url": "https://x.test/sent"}, "", 0, None, tracker=self.gigs, status="ready_to_submit")
        out = self.select(row(title="Done", company="Done Co"), row(title="ByUrl", url="https://x.test/by-url"), row("gig", title="sent", url="https://x.test/sent"), row(title="New"))
        self.assertEqual([i["title"] for i in out["items"]], ["New"])
        self.assertEqual(len(out["skipped"]), 3)

    def test_null_equiv_is_never_selected(self):
        out = self.select(row("gig", title="NoBudget", idr=None))
        self.assertEqual(out["items"], [])
        self.assertIn("needs budget review", out["skipped"][0]["skip_reason"])

    def test_default_limit_takes_the_ten_best_paid_and_defers_the_rest(self):
        rows = [row(title=f"J{i}", idr=10_000_000 + i) for i in range(250)]
        out = self.select(*rows)
        self.assertEqual(len(out["items"]), 10)
        self.assertEqual(out["items"][0]["title"], "J249")
        self.assertEqual({r["skip_reason"] for r in out["skipped"]}, {"beyond the limit of 10 this run"})
        self.assertEqual(len(self.select(*rows, limit=100)["items"]), 100)
        self.assertEqual(len(self.select(*rows, limit=25, max_items=3)["items"]), 3)
        with self.assertRaises(sg.Refused):
            self.select(*rows, limit=0)

    def test_posting_age_gate_applies_to_jobs_and_gigs(self):
        out = self.select(row(title="Edge", posted_date="2026-10-17"), row(title="Old", posted_date="2026-10-16"), row("gig", title="OldGig", posted_date="2026-10-01"),
                          row("gig", title="NewGig", posted_date="2026-10-30T08:00:00Z"), row(title="Undated", posted_date=None), row(title="Garbled", posted_date="ASAP"))
        self.assertEqual(sorted(i["title"] for i in out["items"]), ["Edge", "NewGig"])
        why = {r["title"]: r["skip_reason"] for r in out["skipped"]}
        self.assertEqual(why["Old"], "posted 15 days ago, older than 14 days")
        self.assertIn("older than 14 days", why["OldGig"])
        self.assertIn("date unknown", why["Undated"])
        self.assertIn("date unknown", why["Garbled"])

    def test_stale_postings_leave_the_not_applied_lists_but_undated_stay(self):
        out = self.select(row(title="OldNV", section="needs_verification", posted_date="2026-09-01"), row(title="NewNV", section="needs_verification"),
                          row(title="NoDateNV", section="needs_verification", posted_date=None))
        self.assertEqual(sorted(r["title"] for r in out["listed"]["needs_verification"]), ["NewNV", "NoDateNV"])

    def test_rows_carry_the_posting_date_from_jobs_and_gigs(self):
        self.assertEqual(ap.job_row("k", {"posted_date": "2026-10-20"})["posted_date"], "2026-10-20")
        self.assertEqual(ap.gig_row(gig(posted_at="2026-10-21"))["posted_date"], "2026-10-21")

    def test_sent_with_no_tracker_row_is_never_selected_again(self):
        self.ledger.write_text(json.dumps({"submissions": [{"company": "Led Co", "role": "Led", "url": "https://x.test/led"}]}), encoding="utf-8")
        mailed, gig_mailed, unsent = row(title="Mailed"), row("gig", title="GigMailed"), row(title="Unsent")
        self.queue.write_text(json.dumps({"items": [
            {"id": es.item_id(mailed), "status": "sent", "url": "https://other.test/1"},
            {"id": "x", "status": "sending", "url": gig_mailed["url"] + "/?utm_source=a"},
            {"id": es.item_id(unsent), "status": "not_sent", "url": unsent["url"]},
        ]}), encoding="utf-8")
        out = self.select(row(title="Led", company="Led Co"), mailed, gig_mailed, unsent, row(title="New"))
        self.assertEqual(sorted(i["title"] for i in out["items"]), ["New", "Unsent"])
        self.assertEqual({r["skip_reason"] for r in out["skipped"]}, {"already sent"})

    def test_weak_fit_stays_out_unless_lowered(self):
        self.assertEqual(self.select(row(fit=30))["items"], [])
        self.assertEqual(len(self.select(row(fit=30), min_fit=20)["items"]), 1)

    def test_only_flag_filters(self):
        out = self.select(row(title="J"), row("gig", title="G"), only="gig")
        self.assertEqual([i["type"] for i in out["items"]], ["gig"])


class BatchTests(Base):
    def make_run(self, *rows, **kw):
        return self.select(*rows, **kw)

    def test_one_failure_does_not_stop_the_batch(self):
        run = self.make_run(row(title="A", idr=3e7), row(title="B", idr=2e7), row(title="C", idr=1e7))
        order = []

        def worker(item):
            if item["title"] == "B":
                raise RuntimeError("lualatex failed")
            return {"status": "prepared"}

        while (item := ap.next_item(run)) is not None:
            order.append(item["title"])
            try:
                ap.mark(run, item["id"], **worker(item))
            except RuntimeError as exc:
                ap.mark(run, item["id"], "failed", reason=str(exc))
        self.assertEqual(order, ["A", "B", "C"])
        self.assertEqual([i["status"] for i in run["items"]], ["prepared", "failed", "prepared"])

    def add_tracker_row(self, company, role):
        with self.jobs.open("a", encoding="utf-8") as fh:
            fh.write(f"2026-10-31,{company},{role},,drafted,,\n")

    def finish(self, run):
        return ap.finish(run, queue=self.queue, job_tracker=self.jobs, gig_tracker=self.gigs, today=TODAY, profile=PROFILE)

    def test_non_email_items_end_ready_to_submit_each_in_its_tracker(self):
        run = self.make_run(row(title="Ats", company="Ats Co"), row(title="Portal", company="Portal Co", apply_method="portal_login"),
                            row("gig", title="Gig", url="https://www.upwork.com/jobs/~01g"))
        self.add_tracker_row("Ats Co", "Ats")
        self.add_tracker_row("Portal Co", "Portal")
        for item in run["items"]:
            ap.mark(run, item["id"], "prepared", cv="cv.pdf", cover="cover.pdf", proposal="proposal.txt")
        self.finish(run)
        self.assertEqual([i["status"] for i in run["items"]], ["ready_to_submit"] * 3)
        jobs = self.jobs.read_text(encoding="utf-8")
        self.assertEqual(jobs.count("ready_to_submit"), 2)
        self.assertNotIn("Gig", jobs)
        gigs = self.gigs.read_text(encoding="utf-8")
        self.assertIn("ready_to_submit", gigs)
        self.assertNotIn("Ats", gigs)
        gig_list = next(i["checklist"] for i in run["items"] if i["type"] == "gig")
        self.assertEqual((gig_list["proposal"], gig_list["cv_pdf"]), ("proposal.txt", "cv.pdf"))
        job_list = next(i["checklist"] for i in run["items"] if i["type"] == "job")
        self.assertEqual(job_list["cover_letter_pdf"], "cover.pdf")
        self.assertIn("/outcome", job_list["after_sending"])
        self.assertIn({"question": "Full name", "answer": "Muhammad Ilham Ghazali"}, job_list["screening_answers"])

    def test_a_prepared_gig_can_still_be_recorded_as_proposed_once(self):
        g = {"title": "G", "platform": "Upwork", "gig_id": "1", "url": "https://www.upwork.com/jobs/~011"}
        fg.record(g, "", 0, None, tracker=self.gigs, status="ready_to_submit")
        self.assertFalse(fg.already_proposed(self.gigs, g))
        fg.record(g, "20", 8, None, tracker=self.gigs)
        self.assertTrue(fg.already_proposed(self.gigs, g))
        self.assertEqual(self.gigs.read_text(encoding="utf-8").count("Upwork"), 1)
        with self.assertRaises(sg.Refused):
            fg.record(g, "20", 8, None, tracker=self.gigs)

    def email_run(self, reply, *, dry_run=False):
        pdf = self.dir / "cv.pdf"
        pdf.write_bytes(b"%PDF")
        run = self.make_run(row(title="Mail", company="Acme", apply_method="email", to="hr@acme.io", url="https://x.test/m", idr=20_000_000), row(title="Form", company="Form Co"), dry_run=dry_run)
        self.add_tracker_row("Acme", "Mail")
        self.add_tracker_row("Form Co", "Form")
        paths = {"job_tracker": self.jobs, "ledger": self.ledger, "gig_tracker": self.gigs}
        for item in run["items"]:
            ap.mark(run, item["id"], "prepared", cv=str(pdf), cover=str(pdf))
        mail = run["items"][0]
        out = es.enqueue(mail, "I build Flutter apps.", "Send your CV to hr@acme.io", str(pdf), str(pdf), queue=self.queue, profile="Flutter", recruiters=set(), **paths)
        self.assertEqual(out["status"], "pending", out["reasons"])
        sent = None
        if not dry_run:
            es.approve(reply, queue=self.queue)
            handed = es.next_email(queue=self.queue, sleeper=lambda s: None, **paths)
            if handed["status"] == "ready":
                sent = handed["id"]
                es.mark_sent(sent, "gmail-1", queue=self.queue, **paths)
        self.finish(run)
        return run, sent

    def test_only_email_items_are_sent_and_end_applied(self):
        run, sent = self.email_run("yes")
        self.assertIsNotNone(sent)
        self.assertEqual([i["status"] for i in run["items"]], ["emailed", "ready_to_submit"])
        self.assertEqual(run["items"][0]["message_id"], "gmail-1")
        text = self.jobs.read_text(encoding="utf-8")
        self.assertRegex(text, r"Acme,Mail,email,applied")
        self.assertRegex(text, r"Form Co,Form,[^,]*,ready_to_submit")

    def test_no_or_no_reply_sends_nothing_and_keeps_documents_for_submit(self):
        for reply in ("no", ""):
            with self.subTest(reply=reply):
                self.jobs.write_text("date,company,role,channel,status,notes,source\n", encoding="utf-8")
                self.queue.unlink(missing_ok=True)
                run, sent = self.email_run(reply)
                self.assertIsNone(sent)
                self.assertEqual([i["status"] for i in run["items"]], ["ready_to_submit"] * 2)
                self.assertNotIn(",applied", self.jobs.read_text(encoding="utf-8"))

    def test_dry_run_sends_nothing_and_writes_no_status(self):
        before_row = "drafted"
        run, sent = self.email_run(None, dry_run=True)
        self.assertIsNone(sent)
        text = self.jobs.read_text(encoding="utf-8")
        self.assertNotIn("ready_to_submit", text)
        self.assertEqual(text.count(before_row), 2)
        self.assertEqual(es.pending(es.load_queue(self.queue)), [])
        self.assertTrue(all(i.get("checklist") for i in run["items"]))

    def test_needs_review_email_is_reported_not_sent(self):
        pdf = self.dir / "cv.pdf"
        pdf.write_bytes(b"%PDF")
        run = self.make_run(row(title="Mail", company="Acme", apply_method="email", to="acme.hr@gmail.com"))
        ap.mark(run, 1, "prepared", cv=str(pdf), cover=str(pdf))
        out = es.enqueue(run["items"][0], "Flutter.", "Send your CV to acme.hr@gmail.com", str(pdf), str(pdf), queue=self.queue, profile="Flutter", recruiters=set(),
                         job_tracker=self.jobs, ledger=self.ledger, gig_tracker=self.gigs)
        self.assertEqual(out["status"], "needs_review")
        self.finish(run)
        self.assertEqual(run["items"][0]["status"], "needs_review")
        self.assertIn("free-mail", run["items"][0]["reason"])


class NoBrowserTests(Base):
    def test_autopilot_tools_never_launch_a_browser(self):
        run = self.select(row(title="A", company="A Co"))
        with self.jobs.open("a", encoding="utf-8") as fh:
            fh.write("2026-10-31,A Co,A,,drafted,,\n")
        ap.mark(run, 1, "prepared")
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("a subprocess was started")), \
                mock.patch.object(fg, "open_browser", side_effect=AssertionError("browser opened")):
            ap.finish(run, queue=self.queue, job_tracker=self.jobs, gig_tracker=self.gigs, today=TODAY, profile=PROFILE)
            ap.report(run)
        self.assertEqual(run["items"][0]["status"], "ready_to_submit")

    def test_no_browser_code_in_submit_or_autopilot_sources(self):
        for tool in ("submit_guard.py", "autopilot.py", "email_send.py"):
            src = (ROOT / "tools" / tool).read_text(encoding="utf-8")
            with self.subTest(tool=tool):
                self.assertNotIn("playwright-cli", src)
                self.assertNotIn("playwright_runner(", src)
                self.assertNotIn("subprocess", src)
        for name in ("fill", "submit", "login", "open_browser", "validate_plan"):
            self.assertFalse(hasattr(sg, name), name)

    def test_submit_and_autopilot_commands_are_browser_free(self):
        for cmd in ("submit.md", "autopilot.md"):
            text = (ROOT / ".claude" / "commands" / cmd).read_text(encoding="utf-8")
            with self.subTest(cmd=cmd):
                self.assertNotIn("playwright-cli", text)
                self.assertNotIn("submit_guard.py fill", text)
                self.assertNotIn("submit_guard.py open", text)
                self.assertNotIn(".browser-profile", text)

    def test_browser_profile_stays_gitignored(self):
        self.assertEqual(subprocess.run(["git", "check-ignore", "-q", ".browser-profile/Default/Cookies"], cwd=ROOT).returncode, 0)


class SubmitCommandTests(unittest.TestCase):
    def test_submit_is_email_only_with_a_checklist_for_the_rest(self):
        text = (ROOT / ".claude" / "commands" / "submit.md").read_text(encoding="utf-8")
        for needle in ("tools/autopilot.py checklist", "email_send.py enqueue", "approve --only", "/outcome <job> applied", "humanizer:humanizer"):
            self.assertIn(needle, text)

    def test_checklist_for_a_non_email_job(self):
        out = ap.checklist({"type": "job", "company": "A", "title": "T", "apply_method": "ats_form", "url": "https://x.test/1", "cv": "c.pdf", "cover": "d.pdf"}, PROFILE)
        self.assertEqual((out["link"], out["cv_pdf"], out["cover_letter_pdf"]), ("https://x.test/1", "c.pdf", "d.pdf"))
        self.assertTrue(out["screening_answers"])

    def test_autopilot_command_asks_once_and_spends_nothing(self):
        text = (ROOT / ".claude" / "commands" / "autopilot.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("Send all? (yes / no / exclude 2,5)"), 1)
        self.assertRegex(text, r"never spends Upwork Connects or Freelancer bids")

    def test_approving_and_sending_keep_prompting(self):
        allow = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        for sub in ("approve", "next", "send-next", "mark-sent", "mark-failed"):
            for exe in ("python", "python3"):
                self.assertNotIn(f"Bash({exe} tools/email_send.py {sub}:*)", allow)
        self.assertFalse([a for a in allow if re.fullmatch(r"Bash\(python3? tools/email_send\.py:\*\)", a)])

    def test_new_state_is_gitignored(self):
        for path in ("job_scraper/email_queue.json", "job_scraper/autopilot_run.json", "job_scraper/rank_combined.json", "freelance_tracker.csv"):
            with self.subTest(path=path):
                self.assertEqual(subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode, 0)


class ReportTests(Base):
    def test_counts_per_type_and_estimate(self):
        run = self.select(row(title="A"), row(title="B", idr=9e6), row("gig", title="G", idr=8e6))
        ap.mark(run, 1, "failed", reason="x")
        ap.mark(run, 2, "needs_review", reason="y")
        run["items"][2]["status"] = "ready_to_submit"
        out = ap.report(run)
        self.assertEqual(out["counts"]["job"]["failed"], 1)
        self.assertEqual(out["counts"]["job"]["needs_review"], 1)
        self.assertEqual(out["counts"]["gig"]["ready_to_submit"], 1)
        self.assertEqual([r["id"] for r in out["table"]], [1, 2, 3])
        self.assertIn("not a measurement", out["token_estimate"]["note"])


if __name__ == "__main__":
    unittest.main()
