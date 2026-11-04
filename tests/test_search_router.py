import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import search_router as sr  # noqa: E402


class FirecrawlRotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "fc.json"

    def route(self, env, fn):
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("FIRECRAWL", "TAVILY", "BRAVE"))}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True), mock.patch.object(sr, "firecrawl_search", fn):
            return sr.route("q", 3, firecrawl_state=self.state, tavily_state=self.tmp / "t.json", brave_state=self.tmp / "b.json")

    def test_keys_in_numeric_order(self):
        env = {"FIRECRAWL_API_KEY_10": "c", "FIRECRAWL_API_KEY_2": "b", "FIRECRAWL_API_KEY": "a"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(sr.firecrawl_key_names(), ["FIRECRAWL_API_KEY", "FIRECRAWL_API_KEY_2", "FIRECRAWL_API_KEY_10"])

    def test_exhausted_key_is_parked_and_next_key_used(self):
        def fn(q, n, key):
            if key == "k1":
                raise sr.KeyParked("Firecrawl HTTP 402")
            return [{"title": "t", "url": "u", "snippet": "s"}]
        out = self.route({"FIRECRAWL_API_KEY_1": "k1", "FIRECRAWL_API_KEY_2": "k2"}, fn)
        self.assertEqual((out["provider"], out["key"]), ("firecrawl", "FIRECRAWL_API_KEY_2"))
        self.assertEqual(sr.parked(self.state), {"FIRECRAWL_API_KEY_1"})
        self.assertNotIn("k1", self.state.read_text())

    def test_all_keys_dead_falls_through_to_other_providers(self):
        def dead(q, n, key):
            raise sr.KeyParked("Firecrawl HTTP 402")
        out = self.route({"FIRECRAWL_API_KEY_1": "k1"}, dead)
        self.assertIsNone(out["provider"])
        self.assertTrue(any("TAVILY_API_KEY not set" in e for e in out["errors"]))

        def never(q, n, key):
            self.fail("parked key must not be retried")
        again = self.route({"FIRECRAWL_API_KEY_1": "k1"}, never)
        self.assertIsNone(again["provider"])


if __name__ == "__main__":
    unittest.main()
