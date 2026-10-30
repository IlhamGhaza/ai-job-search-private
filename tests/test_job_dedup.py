"""Cross-source dedup within one /scrape run (tools/job_dedup.py)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import job_dedup as jd  # noqa: E402


def j(**kw):
    base = {"id": "1", "portal": "x-search", "title": "Junior Flutter Developer", "company": "Acme", "location": "Berlin", "url": "https://x.example/1"}
    base.update(kw)
    return base


class DedupTests(unittest.TestCase):
    def test_canonical_url_drops_tracking_and_www(self):
        self.assertEqual(
            jd.canonical_url("https://www.Example.com/jobs/1/?utm_source=freehire.me&gh_src=abc&id=5#apply"),
            "https://example.com/jobs/1?id=5",
        )

    def test_same_stable_id_merges(self):
        out = jd.dedupe([j(), j(url="https://x.example/1?ref=feed")])
        self.assertEqual(out["counts"]["duplicates"], 1)

    def test_same_url_across_portals_merges_and_prefers_employer_listing(self):
        board = j(portal="remotive-search", id="r1", url="https://remotive.com/remote-jobs/1", apply_url="https://boards.greenhouse.io/acme/jobs/7")
        ats = j(portal="ats-search", id="greenhouse:acme:7", url="https://boards.greenhouse.io/acme/jobs/7?gh_src=x", salary_min=None)
        out = jd.dedupe([board, ats])
        self.assertEqual(len(out["jobs"]), 1)
        primary = out["jobs"][0]
        self.assertEqual(primary["portal"], "ats-search")
        self.assertEqual(primary["also_seen_at"][0]["portal"], "remotive-search")

    def test_company_title_location_merges_only_when_all_known(self):
        a = j(portal="a-search", id="1", url="https://a.example/1", company="Acme GmbH")
        b = j(portal="b-search", id="2", url="https://b.example/2", company="ACME")
        self.assertEqual(len(jd.dedupe([a, b])["jobs"]), 1)

    def test_uncertain_matches_are_not_merged(self):
        a = j(portal="a-search", id="1", url="https://a.example/1", location="Berlin")
        b = j(portal="b-search", id="2", url="https://b.example/2", location="Munich")
        c = j(portal="c-search", id="3", url="https://c.example/3", location=None)
        out = jd.dedupe([a, b, c])
        self.assertEqual(len(out["jobs"]), 3)
        self.assertEqual(out["counts"]["possible_duplicates"], 1)

    def test_linkedin_post_is_linked_not_merged(self):
        listing = j(portal="ats-search", id="g1", url="https://boards.greenhouse.io/acme/jobs/1")
        post = {"source_type": "social_post", "portal": "linkedin-posts-search", "id": "p", "url": "https://www.linkedin.com/posts/x",
                "title": "Jane on LinkedIn: Acme is hiring a Junior Flutter Developer", "description": "DM me"}
        out = jd.dedupe([post, listing])
        self.assertEqual(len(out["jobs"]), 2)
        self.assertEqual(out["counts"]["linked_posts"], 1)
        linked = next(x for x in out["jobs"] if x.get("source_type") == "social_post")
        self.assertEqual(linked["linked_listing"], listing["url"])

    def test_merge_fills_gaps_never_overwrites(self):
        a = j(portal="ats-search", id="g", url="https://boards.greenhouse.io/acme/jobs/1", salary_min=None, deadline="2026-12-01")
        b = j(portal="b-search", id="2", url="https://boards.greenhouse.io/acme/jobs/1", salary_min=5000, deadline="2027-01-01")
        merged = jd.dedupe([a, b])["jobs"][0]
        self.assertEqual(merged["salary_min"], 5000)
        self.assertEqual(merged["deadline"], "2026-12-01")


if __name__ == "__main__":
    unittest.main()
