"""Wiring for the freelance gig skills, /gigs and /propose.

Each freelance skill follows the portal contract (search/detail CLI, enabled:
flag, offline tests, url-reference.md, pre-approved CLI) and is marked
`category: freelance` so /scrape keeps gigs out of job results. Freelance
state stays out of git and away from the job tracker.
"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"
FREELANCE = ["upwork-search", "freelancer-search", "contra-search", "peopleperhour-search", "guru-search", "workana-search",
             "twine-search", "projects-co-id-search", "fastwork-search"]
ENABLED = re.compile(r"^enabled:\s*(true|false)\b", re.M)
CATEGORY = re.compile(r"^category:\s*freelance\b", re.M)


def frontmatter(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    return text[: text.find("\n---", 4)]


def gigs_runs(skill_md: Path) -> bool:
    """/gigs Step 1: a freelance skill runs unless enabled: false (missing key = enabled)."""
    fm = frontmatter(skill_md)
    m = ENABLED.search(fm)
    return bool(CATEGORY.search(fm)) and (m is None or m.group(1) == "true")


class FreelanceSkillContractTests(unittest.TestCase):
    def test_every_freelance_skill_has_the_contract_files(self):
        for name in FREELANCE:
            base = SKILLS / name
            with self.subTest(skill=name):
                for rel in ("SKILL.md", "url-reference.md", "cli/package.json", "cli/tsconfig.json", "cli/src/cli.ts", "cli/src/helpers.ts",
                            "cli/src/gig.ts", "cli/src/brave.ts", "cli/src/commands/search.ts", "cli/src/commands/detail.ts"):
                    self.assertTrue((base / rel).is_file(), rel)
                self.assertTrue(list((base / "cli" / "tests").glob("*.test.ts")), "offline tests")
                fm = frontmatter(base / "SKILL.md")
                self.assertRegex(fm, ENABLED, "explicit enabled: flag")
                self.assertRegex(fm, CATEGORY, "category: freelance")

    def test_zero_runtime_dependencies(self):
        for name in FREELANCE:
            pkg = json.loads((SKILLS / name / "cli" / "package.json").read_text(encoding="utf-8"))
            with self.subTest(skill=name):
                self.assertEqual(pkg.get("dependencies"), {})
                self.assertFalse(set(pkg.get("scripts", {})) & {"preinstall", "install", "postinstall", "prepare"})

    def test_shared_kits_are_identical_copies(self):
        kit = SKILLS / "remotive-search" / "cli" / "src" / "helpers.ts"
        for file in ("helpers.ts", "gig.ts", "brave.ts"):
            copies = {(SKILLS / n / "cli" / "src" / file).read_text(encoding="utf-8") for n in FREELANCE}
            with self.subTest(file=file):
                self.assertEqual(len(copies), 1, f"{file} drifted between freelance skills")
        self.assertEqual((SKILLS / "upwork-search" / "cli" / "src" / "helpers.ts").read_text(encoding="utf-8"), kit.read_text(encoding="utf-8"))

    def test_enabled_false_is_honoured_by_gigs(self):
        skill = SKILLS / "contra-search" / "SKILL.md"
        self.assertTrue(gigs_runs(skill))
        tmp = Path(tempfile.mkdtemp()) / "SKILL.md"
        tmp.write_text(skill.read_text(encoding="utf-8").replace("enabled: true", "enabled: false", 1), encoding="utf-8")
        self.assertFalse(gigs_runs(tmp))
        self.assertFalse(gigs_runs(SKILLS / "remotive-search" / "SKILL.md"), "job portals are not gig sources")

    def test_upwork_skill_never_names_an_upwork_page_fetch(self):
        # Its own code only POSTs to the GraphQL API; GETs live in the shared kit and go to Brave.
        src = "\n".join(p.read_text(encoding="utf-8") for p in (SKILLS / "upwork-search" / "cli" / "src" / "commands").glob("*.ts"))
        for call in ("httpGet(", "getJson(", "fetch(", "fetchPostingPage"):
            self.assertNotIn(call, src)
        self.assertIn("postJson", src)


class PermissionsAndIgnoreTests(unittest.TestCase):
    def setUp(self):
        self.allow = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        self.guards = (ROOT / "tools" / "security_guards.py").read_text(encoding="utf-8")

    def test_each_cli_is_pre_approved_in_settings_and_guards(self):
        for name in FREELANCE:
            entry = f"Bash(bun run .agents/skills/{name}/cli/src/cli.ts:*)"
            with self.subTest(skill=name):
                self.assertIn(entry, self.allow)
                self.assertIn(f'"{entry}"', self.guards)

    def test_only_read_only_freelance_commands_are_pre_approved(self):
        for ok in ("Bash(python tools/gig_rules.py evaluate:*)", "Bash(python tools/freelance_guard.py check:*)",
                   "Bash(python tools/freelance_guard.py humanizer-check:*)"):
            self.assertIn(ok, self.allow)
        for risky in ("fill", "send", "record", "login", "open", "email-draft"):
            for exe in ("python", "python3"):
                self.assertNotIn(f"Bash({exe} tools/freelance_guard.py {risky}:*)", self.allow)
        self.assertNotIn("Bash(python tools/freelance_guard.py:*)", self.allow)

    def test_freelance_state_is_gitignored(self):
        for path in ("freelance_tracker.csv", "job_scraper/gigs_latest.json", ".browser-profile/Default/Cookies",
                     ".submit-screenshots/freelance/upwork_1_review.png", "documents/applications/freelance/upwork_1/gig.json", ".env"):
            proc = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
            with self.subTest(path=path):
                self.assertEqual(proc.returncode, 0, f"{path} must be gitignored")


class SeparationTests(unittest.TestCase):
    def test_scrape_skips_freelance_skills(self):
        text = (ROOT / ".claude" / "skills" / "job-scraper" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("category: freelance", text)
        self.assertRegex(text, r"`/scrape` never does")

    def test_freelance_tools_never_touch_the_job_tracker_or_seen_jobs(self):
        for tool in ("gig_rules.py", "freelance_guard.py"):
            src = (ROOT / "tools" / tool).read_text(encoding="utf-8")
            with self.subTest(tool=tool):
                self.assertNotIn("job_search_tracker.csv", src)
                self.assertNotIn("seen_jobs.json", src)

    def test_submit_email_runs_the_humanizer_and_its_claim_check(self):
        text = (ROOT / ".claude" / "commands" / "submit.md").read_text(encoding="utf-8")
        step = text[text.index("## Step 2a") : text.index("## Step 2b")]
        for needle in ("humanizer-status", "humanizer:humanizer", "humanizer-check"):
            self.assertIn(needle, step)
        self.assertLess(step.index("humanizer-check"), step.index("email-draft"))

    def test_commands_exist_and_keep_the_safeguards(self):
        gigs = (ROOT / ".claude" / "commands" / "gigs.md").read_text(encoding="utf-8")
        propose = (ROOT / ".claude" / "commands" / "propose.md").read_text(encoding="utf-8")
        self.assertIn("tools/gig_rules.py evaluate", gigs)
        self.assertIn("Vetted networks", gigs)
        for needle in ("posting_guard.py", "freelance_guard.py check", "claims-check", "humanizer-status", "humanizer-check",
                       "fill only", "explicit **yes**", "--approve-spend", "One gig per call", "freelance_tracker.csv"):
            with self.subTest(needle=needle):
                self.assertIn(needle, propose)


if __name__ == "__main__":
    unittest.main()
