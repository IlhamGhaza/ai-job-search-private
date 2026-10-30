"""Wiring for the global junior-Flutter portal skills.

Each new portal must follow the shipped contract: an `enabled:` toggle that
/scrape honours, a pre-approved CLI entry in settings.json and in
security_guards.py, offline tests, and a url-reference.md. The personal state
the new tools write (FX cache, submission ledger, browser profile,
screenshots) must be gitignored.
"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW_PORTALS = [
    "ats-search", "remotive-search", "remoteok-search", "himalayas-search", "jobicy-search", "weworkremotely-search",
    "arbeitnow-search", "platsbanken-search", "nav-search", "mycareersfuture-search", "linkedin-posts-search",
    "jobstreet-search", "jobsites-search",
]
ENABLED = re.compile(r"^enabled:\s*(true|false)\b", re.M)


def portal_enabled(skill_md: Path) -> bool:
    """/scrape Step 1b: a missing key means enabled."""
    m = ENABLED.search(skill_md.read_text(encoding="utf-8"))
    return m is None or m.group(1) == "true"


class NewPortalWiringTests(unittest.TestCase):
    def test_every_new_portal_has_the_contract_files(self):
        for name in NEW_PORTALS:
            base = ROOT / ".agents" / "skills" / name
            with self.subTest(portal=name):
                for rel in ("SKILL.md", "url-reference.md", "cli/package.json", "cli/src/cli.ts", "cli/src/helpers.ts",
                            "cli/src/commands/search.ts", "cli/src/commands/detail.ts"):
                    self.assertTrue((base / rel).is_file(), rel)
                self.assertTrue(list((base / "cli" / "tests").glob("*.test.ts")), "offline tests")
                self.assertIsNotNone(ENABLED.search((base / "SKILL.md").read_text(encoding="utf-8")), "explicit enabled: flag")

    def test_enabled_false_is_honoured_like_scrape(self):
        skill = ROOT / ".agents" / "skills" / "remotive-search" / "SKILL.md"
        self.assertTrue(portal_enabled(skill))
        tmp = Path(tempfile.mkdtemp()) / "SKILL.md"
        tmp.write_text(skill.read_text(encoding="utf-8").replace("enabled: true", "enabled: false", 1), encoding="utf-8")
        self.assertFalse(portal_enabled(tmp))

    def test_shared_helpers_are_identical_copies(self):
        copies = {(ROOT / ".agents" / "skills" / n / "cli" / "src" / "helpers.ts").read_text(encoding="utf-8") for n in NEW_PORTALS}
        self.assertEqual(len(copies), 1, "the shared portal kit drifted between skills; copy one version to all")

    def test_each_cli_is_pre_approved_in_settings_and_guards(self):
        allow = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        guards = (ROOT / "tools" / "security_guards.py").read_text(encoding="utf-8")
        for name in NEW_PORTALS:
            entry = f"Bash(bun run .agents/skills/{name}/cli/src/cli.ts:*)"
            with self.subTest(portal=name):
                self.assertIn(entry, allow)
                self.assertIn(f'"{entry}"', guards)

    def test_only_read_only_rule_commands_are_pre_approved(self):
        allow = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        self.assertIn("Bash(python tools/submit_guard.py check:*)", allow)
        for risky in ("Bash(python tools/submit_guard.py:*)", "Bash(python tools/submit_guard.py submit:*)",
                      "Bash(python tools/submit_guard.py record:*)", "Bash(python tools/job_rules.py mark-safety:*)"):
            self.assertNotIn(risky, allow)

    def test_personal_state_is_gitignored(self):
        for path in ("job_scraper/fx_rates.json", "job_scraper/submissions.json", ".browser-profile/Default/Cookies",
                     ".submit-screenshots/acme_review.png"):
            proc = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
            with self.subTest(path=path):
                self.assertEqual(proc.returncode, 0, f"{path} must be gitignored")

    def test_untouched_reference_portals_keep_their_contract(self):
        for name in ("linkedin-search", "freehire-search"):
            text = (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(portal=name):
                self.assertIn(f"allowed-tools: Bash(bun run .agents/skills/{name}/cli/src/cli.ts *)", text)

    def test_submit_command_keeps_its_safety_promises(self):
        text = (ROOT / ".claude" / "commands" / "submit.md").read_text(encoding="utf-8")
        for promise in ("explicit \"yes\"", "One job per call", "Never handle credentials", "fill_only", "Terms of Use",
                        "never upload ID", "Never submit twice"):
            with self.subTest(promise=promise):
                self.assertIn(promise, text)


if __name__ == "__main__":
    unittest.main()
