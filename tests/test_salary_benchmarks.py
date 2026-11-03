"""Salary floor config, benchmark tiers, net-vs-living-cost onsite rule, relocation and the prose lint (offline)."""

import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import autopilot as ap  # noqa: E402
import connector_sources as cs  # noqa: E402
import fx_rates  # noqa: E402
import gig_rules  # noqa: E402
import job_rules as jr  # noqa: E402
import pay_lint  # noqa: E402

TODAY = date(2026, 11, 2)
# Units of currency per 1 IDR: 1 USD = 16,000, 1 EUR = 17,500, 1 MYR = 3,600, 1 INR = 190, 1 SGD = 12,000.
FX = fx_rates.FxTable({"USD": 1 / 16000, "EUR": 1 / 17500, "MYR": 1 / 3600, "INR": 1 / 190, "SGD": 1 / 12000}, "2026-11-01", "test")
FLOOR = 5_729_876


def fixture_config(**over) -> dict:
    """A small, fixed config so tier maths does not move when the real table is refreshed."""
    def sal(cur, low, median, high):
        return {"currency": cur, "period": "month", "low": low, "median": median, "high": high, "sources": []}

    def col(amount, cur="USD"):
        return {"monthly": amount, "currency": cur, "sources": []}

    data = {
        "updated": "2026-11-01", "stale_after_days": 90,
        "salary_floor_idr_monthly": {"value": FLOOR, "source": "UMP DKI Jakarta 2026", "year": 2026},
        "hours_per_month": 173, "home_country": "ID", "unknown_tax_rate": 0.30, "tier_a_multiple": 2.0, "tolerance": 0.05,
        "relocation_countries": ["US", "DE", "MY", "VN", "BN"],
        "countries": {
            "US": {"salary": sal("USD", 4000, 5500, 7500), "cost_of_living": col(4700), "tax": {"rate": 0.23}},
            "DE": {"salary": sal("EUR", 3000, 4300, 4600), "cost_of_living": col(2400), "tax": {"rate": 0.35}},
            "MY": {"salary": sal("MYR", 3500, 4000, 6000), "cost_of_living": col(1000), "tax": {"rate": 0.15}},
            # Average/median above the floor, but the low end (P25) below it: tier C.
            "VN": {"salary": sal("USD", 300, 900, 1200), "cost_of_living": col(780), "tax": {"rate": 0.12}},
            "BN": {"salary": sal("USD", 1500, 2000, 3000), "cost_of_living": col(1150), "tax": None},
            "IN": {"salary": sal("INR", 24000, 37500, 83000), "cost_of_living": col(530), "tax": None},
            "ID": {
                "salary": sal("IDR", 3_460_000, 6_000_000, 9_000_000),
                "salary_groups": {"jabodetabek": sal("IDR", FLOOR, 7_000_000, 10_000_000)},
                "cost_of_living": col(FLOOR, "IDR"), "tax": {"rate": 0.0},
                "cities": {
                    "jakarta": {"name": "DKI Jakarta", "match": ["jakarta"], "region": "jabodetabek", "cost_of_living": col(FLOOR, "IDR")},
                    "kota_bekasi": {"name": "Kota Bekasi", "match": ["kota bekasi"], "region": "jabodetabek", "cost_of_living": col(5_999_443, "IDR")},
                    "surabaya": {"name": "Kota Surabaya", "match": ["surabaya"], "region": "domestic", "cost_of_living": col(5_288_796, "IDR")},
                },
            },
        },
    }
    data.update(over)
    return data


PAY = jr.PayConfig(fixture_config())


def job(**kw) -> dict:
    base = {"id": "1", "title": "Junior Flutter Developer", "company": "Acme", "location": "Jakarta, Indonesia", "country": "ID",
            "url": "https://boards.greenhouse.io/acme/jobs/1", "portal": "ats-search", "employment_type": "Full-time",
            "description": "Build Flutter apps with BLoC. 1-2 years of experience.", "date": "2026-10-30",
            "salary_min": 8_000_000, "salary_max": None, "salary_currency": "IDR", "salary_period": "month", "evidence": ["Greenhouse"]}
    base.update(kw)
    return base


def ev(pay=PAY, intern=jr.DEFAULT_INTERN_MODE, **kw):
    return jr.evaluate_job(job(**kw), FX, TODAY, watchlist=[], pay=pay, intern=intern)


REMOTE = {"location": "Remote", "country": None, "work_mode": "remote", "remote_eligibility": "Worldwide"}
UNDISCLOSED = {"salary_min": None, "salary_max": None, "salary_currency": None, "salary_period": None}


class FloorConfigTests(unittest.TestCase):
    def test_real_config_floor_is_ump_dki_2026_and_hourly_follows(self):
        self.assertEqual(jr.SALARY_FLOOR_IDR_MONTHLY, FLOOR)
        self.assertEqual(jr.PAY.floor_meta["year"], 2026)
        self.assertEqual(round(jr.PAY.floor / jr.PAY.hours), 33_121)
        self.assertEqual(gig_rules.HOURS_PER_MONTH, jr.PAY.hours)

    def test_floor_change_propagates_to_jobs_and_hourly_gigs(self):
        pay = jr.PayConfig(fixture_config(salary_floor_idr_monthly={"value": 7_000_000}))
        self.assertEqual(ev(pay=pay, salary_min=6_900_000, **REMOTE)["salary"]["status"], "reject")
        self.assertEqual(ev(pay=pay, salary_min=7_000_001, **REMOTE)["salary"]["status"], "pass")
        gig = {"budget_type": "hourly", "budget_min": 40_000, "budget_max": None, "budget_currency": "IDR"}
        self.assertEqual(gig_rules.rate_check(gig, FX, monthly_floor=pay.floor, hours=pay.hours)["floor_idr_hourly"], round(7_000_000 / 173))

    def test_disclosed_above_below_and_exactly_at_the_floor(self):
        self.assertEqual(ev(salary_min=FLOOR + 1, **REMOTE)["salary"]["status"], "pass")
        self.assertEqual(ev(salary_min=FLOOR, **REMOTE)["salary"]["status"], "reject")
        self.assertEqual(ev(salary_min=FLOOR - 1, **REMOTE)["salary"]["status"], "reject")


class TierTests(unittest.TestCase):
    def test_tiers_come_from_the_low_end_not_the_average(self):
        self.assertEqual(PAY.benchmark("US", None, FX)["tier"], "A")
        self.assertEqual(PAY.benchmark("ID", "jakarta", FX)["tier"], "B")
        vn = PAY.benchmark("VN", None, FX)
        self.assertGreater(vn["median_idr"], FLOOR)  # the average is above the floor ...
        self.assertEqual(vn["tier"], "C")            # ... but the low end decides
        self.assertEqual(PAY.benchmark("ID", "surabaya", FX)["tier"], "C")

    def test_undisclosed_in_tier_a_and_b_is_processed_with_a_label(self):
        a = ev(location="Berlin, Germany", country="DE", work_mode="onsite", description="Flutter. 1-2 years. We sponsor your visa.", **UNDISCLOSED)
        self.assertEqual((a["salary"]["status"], a["salary_tier"], a["salary_source"]), ("estimated", "A", "estimated"))
        self.assertIn("salary: estimated (tier A)", a["flags"])
        b = ev(work_mode="onsite", **UNDISCLOSED)
        self.assertEqual((b["salary_tier"], b["section"]), ("B", "confirmed"))
        self.assertIn("salary: estimated (tier B), ask in interview", b["flags"])

    def test_undisclosed_in_tier_c_is_rejected(self):
        r = ev(location="Surabaya, Indonesia", work_mode="onsite", **UNDISCLOSED)
        self.assertEqual(r["section"], "rejected")
        self.assertTrue(any(x.startswith("undisclosed salary in tier C") for x in r["reasons"]), r["reasons"])

    def test_tier_c_place_with_disclosed_pay_above_the_floor_is_accepted(self):
        r = ev(location="Surabaya, Indonesia", work_mode="onsite", salary_min=8_000_000)
        self.assertNotEqual(r["section"], "rejected", r["reasons"])
        self.assertEqual(r["salary"]["status"], "pass")

    def test_remote_uses_the_employer_country_and_unknown_is_tier_b(self):
        us = ev(employer_country="US", **UNDISCLOSED, **REMOTE)
        self.assertEqual((us["salary_tier"], us["salary_estimate"]["basis"]), ("A", "employer country"))
        unknown = ev(**UNDISCLOSED, **REMOTE)
        self.assertEqual(unknown["salary_tier"], "B")
        self.assertIn("employer country unknown", unknown["salary_estimate"]["basis"])
        vn = ev(employer_country="Vietnam", **UNDISCLOSED, **REMOTE)
        self.assertEqual(vn["section"], "rejected")

    def test_missing_benchmark_is_tier_b_with_a_warning(self):
        r = ev(employer_country="FR", **UNDISCLOSED, **REMOTE)
        self.assertEqual(r["salary_tier"], "B")
        self.assertIn("benchmark missing for FR: tier B assumed", r["flags"])
        out = jr.evaluate([job(employer_country="FR", **UNDISCLOSED, **REMOTE)], FX, TODAY, pay=PAY)
        self.assertEqual(out["benchmarks"]["missing"], ["FR"])

    def test_stale_table_warns(self):
        old = jr.PayConfig(fixture_config(updated="2026-06-01"))
        info = old.staleness(TODAY)
        self.assertTrue(info["stale"])
        self.assertIn("/benchmarks refresh", info["warning"])
        self.assertFalse(PAY.staleness(TODAY)["stale"])
        self.assertTrue(jr.evaluate([job()], FX, TODAY, pay=old)["benchmarks"]["stale"])

    def test_internship_with_undisclosed_pay_is_not_estimated(self):
        r = ev(title="Flutter Developer Intern", **UNDISCLOSED, **REMOTE)
        self.assertEqual(r["section"], "needs_verification")
        self.assertNotEqual(r["salary_source"], "estimated")


class HardRulesStillFirstTests(unittest.TestCase):
    def test_india_onsite_and_cambodia_are_still_rejected(self):
        self.assertEqual(ev(location="Bengaluru, India", country="IN", work_mode="onsite", salary_min=200_000, salary_currency="INR")["section"], "rejected")
        self.assertEqual(ev(location="Phnom Penh, Cambodia", country="KH", work_mode="remote", salary_min=20_000_000)["section"], "rejected")
        self.assertEqual(ev(location="Phnom Penh, Cambodia", country="KH", **UNDISCLOSED)["section"], "rejected")


class AuditFixTests(unittest.TestCase):
    def test_malaysia_onsite_with_visa_support_passes_location(self):
        r = ev(location="Kuala Lumpur, Malaysia", country="MY", work_mode="onsite", salary_min=7_000, salary_currency="MYR",
               description="Flutter. 1-2 years. Visa sponsorship is available.")
        self.assertIsNone(r["location"]["reject"])
        self.assertEqual(r["arrangement"], "relocation: abroad")
        self.assertNotEqual(r["section"], "rejected", r["reasons"])

    def test_remote_us_company_paying_15k_is_flagged_not_rejected(self):
        r = ev(employer_country="US", salary_min=15_000, salary_currency="USD", salary_period="year", **REMOTE)
        self.assertTrue(r["underpaid_for_market"])
        self.assertTrue(any(f.startswith("underpaid_for_market") for f in r["flags"]))
        self.assertNotEqual(r["section"], "rejected")
        below_floor = ev(employer_country="US", salary_min=3_000, salary_currency="USD", salary_period="year", **REMOTE)
        self.assertEqual(below_floor["section"], "rejected")

    def test_jakarta_8_million_onsite_is_not_underpaid(self):
        r = ev(work_mode="onsite", salary_min=8_000_000)
        self.assertFalse(r["underpaid_for_market"])
        self.assertEqual((r["salary"]["status"], r["arrangement"]), ("pass", "onsite (prefers remote)"))
        self.assertIn("onsite (prefers remote)", r["flags"])

    def test_hybrid_berlin_is_treated_as_onsite(self):
        r = ev(location="Berlin, Germany", country="DE", work_mode="hybrid", salary_min=4_000, salary_currency="EUR",
               description="Flutter. 1-2 years. We sponsor your visa.")
        self.assertEqual(r["salary"]["basis"], "net_vs_living_cost")
        self.assertEqual(r["salary"]["tax_rate"], 0.35)
        self.assertEqual(r["arrangement"], "relocation: abroad")
        hybrid_abroad = ev(location="Paris, France", country="FR", work_mode="hybrid")
        self.assertIn("hybrid job in FR: not a relocation country", hybrid_abroad["reasons"])

    def test_surabaya_onsite_is_allowed_as_domestic_relocation_and_ranked_lower(self):
        sby = ev(location="Surabaya, Indonesia", work_mode="onsite", salary_min=8_000_000)
        jkt = ev(work_mode="onsite", salary_min=8_000_000)
        remote = ev(salary_min=8_000_000, **REMOTE)
        self.assertEqual(sby["arrangement"], "relocation: domestic")
        self.assertIn("relocation: domestic", sby["flags"])
        self.assertNotEqual(sby["section"], "rejected")
        key = lambda r: r["rank_key"][5]  # the arrangement slot
        self.assertLess(key(remote), key(sby))
        self.assertLess(key(jkt), key(sby))

    def test_five_point_eight_million_against_a_5_73_million_threshold_needs_verification(self):
        r = ev(work_mode="onsite", salary_min=5_800_000)  # fixture tax for ID is 0%: net = gross
        self.assertEqual(r["salary"]["status"], "needs_salary_verification")
        self.assertIn("within 5%", r["salary"]["reason"])
        # The real table: Rp 5.8 million gross, 6% tax -> Rp 5.45 million net, still within 5% of Rp 5.73 million.
        real = jr.evaluate_job(job(work_mode="onsite", salary_min=5_800_000), FX, TODAY, watchlist=[])
        self.assertEqual(real["salary"]["status"], "needs_salary_verification")

    def test_european_gross_is_converted_to_net_before_the_living_cost_check(self):
        # EUR 2,400 gross = IDR 42.0M; living cost USD 2,400 = IDR 38.4M. Gross would pass; net (35% tax) = IDR 27.3M fails.
        r = ev(location="Berlin, Germany", country="DE", work_mode="onsite", salary_min=2_400, salary_currency="EUR",
               description="Flutter. 1-2 years. We sponsor your visa.")
        self.assertEqual(r["salary"]["status"], "reject")
        self.assertEqual(r["salary"]["net_idr_monthly"], round(2_400 * 17_500 * 0.65))
        self.assertTrue(any(x.startswith("living cost") for x in r["reasons"]))

    def test_unknown_tax_rate_uses_30_percent_and_is_flagged(self):
        r = ev(location="Bandar Seri Begawan, Brunei", country="BN", work_mode="onsite", salary_min=3_000, salary_currency="USD",
               description="Flutter. 1-2 years. We sponsor your visa.")
        self.assertEqual((r["salary"]["tax_rate"], r["salary"]["tax_known"]), (0.30, False))
        self.assertIn("tax rate unknown for BN: 30% assumed", r["flags"])

    def test_threshold_is_the_higher_of_floor_and_living_cost(self):
        bekasi = ev(location="Kota Bekasi, Indonesia", work_mode="onsite", salary_min=6_100_000)
        self.assertEqual(bekasi["salary"]["threshold_idr"], 5_999_443)
        self.assertEqual(bekasi["salary"]["status"], "needs_salary_verification")
        sby = ev(location="Surabaya, Indonesia", work_mode="onsite", salary_min=8_000_000)
        self.assertEqual(sby["salary"]["threshold_idr"], FLOOR)

    def test_relocation_and_search_countries_come_from_one_config(self):
        self.assertEqual(jr.PRIORITY_COUNTRIES, set(jr.PAY.relocation) | {"ID"})
        self.assertEqual(jr.RELOCATION_COUNTRIES, set(jr.PAY.relocation))
        for code in ("MY", "PH", "TH", "VN", "BN", "TL", "SG"):
            self.assertIn(code, jr.PAY.relocation)
        indeed = set(cs.DEFAULTS["indeed"]["countries"].split(","))
        self.assertTrue(indeed <= jr.PRIORITY_COUNTRIES, indeed - jr.PRIORITY_COUNTRIES)


class ProseLintTests(unittest.TestCase):
    def test_the_repo_prose_matches_the_config(self):
        self.assertEqual(pay_lint.check(), [])

    def test_a_different_floor_in_prose_fails(self):
        self.assertTrue(pay_lint.check_text("Remote jobs must clear the salary floor of IDR 6,500,000 a month.", "x.md", PAY))
        self.assertTrue(pay_lint.check_text("Gaji minimal 5 juta per bulan.", "x.md", PAY))
        self.assertTrue(pay_lint.check_text("- Remote (fully or hybrid): PASS", "x.md", PAY))
        self.assertEqual(pay_lint.check_text("The salary floor is IDR 5,729,876/month.", "x.md", PAY), [])

    def test_a_relocation_list_that_drifts_fails(self):
        bad = "- **Open to relocation in:** United States, Germany."
        self.assertTrue(pay_lint.check_text(bad, "CLAUDE.md", PAY))
        good = "- **Open to relocation in:** United States, Germany, Malaysia, Vietnam, Brunei."
        self.assertEqual(pay_lint.check_text(good, "CLAUDE.md", PAY), [])


class ApplyingWithoutSalaryTests(unittest.TestCase):
    def test_suggestion_is_the_rounded_median_and_needs_confirmation(self):
        r = ev(work_mode="onsite", **UNDISCLOSED)
        s = r["expected_salary_suggestion"]
        self.assertEqual((s["amount"], s["currency"], s["needs_confirmation"]), (7_000_000, "IDR", True))

    def test_stored_fields_keep_the_salary_source(self):
        stored = jr.stored_fields(ev(work_mode="onsite", **UNDISCLOSED))
        self.assertEqual((stored["salary_source"], stored["salary_tier"]), ("estimated", "B"))

    def test_autopilot_never_fills_the_expected_salary_and_notes_the_estimate(self):
        r = ev(work_mode="onsite", **UNDISCLOSED)
        item = {"type": "job", "title": "T", "company": "C", "salary_source": "estimated", "salary_tier": "B",
                "expected_salary_suggestion": r["expected_salary_suggestion"]}
        c = ap.checklist(item)
        self.assertIsNone(c["expected_salary"]["value_to_use"])
        self.assertEqual(c["expected_salary"]["status"], "needs_user_confirmation")


class SortingTests(unittest.TestCase):
    def test_combine_lists_disclosed_before_estimated(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = Path(tmp) / "seen.json"
            entries = {
                "e": {"title": "Est", "company": "E", "rules_section": "confirmed", "status": "ranked", "salary_source": "estimated", "salary_tier": "A",
                      "benchmark_median_idr": 90_000_000, "salary_idr_monthly_min": None},
                "d": {"title": "Disc", "company": "D", "rules_section": "confirmed", "status": "ranked", "salary_idr_monthly_min": 8_000_000},
            }
            seen.write_text(json.dumps({"seen": entries}), encoding="utf-8")
            out = ap.combine(seen=seen, since="2026-11-02")
            self.assertEqual([r["title"] for r in out["sections"]["confirmed"]], ["Disc", "Est"])
            self.assertEqual([r["salary_source"] for r in out["sections"]["confirmed"]], ["disclosed", "estimated"])


if __name__ == "__main__":
    unittest.main()
