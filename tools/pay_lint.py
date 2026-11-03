#!/usr/bin/env python3
"""Fails when prose states a pay rule that differs from tools/data/salary_benchmarks.json.

Every pay number lives in the config; prompts and docs only describe it. This
lint catches the drift the repo audit found:
- an IDR amount on a line about the salary floor that is not the configured floor
  (or the hourly floor derived from it);
- the retired floor (IDR 5,000,000 / "5 juta") or its hourly figure (28,902);
- the retired "USD 55,000-65,000" underpaid benchmark;
- "Remote (fully or hybrid)": hybrid is onsite;
- a relocation-country list in CLAUDE.md that differs from the config.

Run from the repo root:
    python tools/pay_lint.py            # exit 1 and a list of problems on drift
Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import job_rules as jr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"node_modules", "graphify-out", "job_scraper", "documents", "cv", "cover_letters", ".git", "tests", "cli"}
SKIP_FILES = {"CHANGELOG.md"}
AMOUNT = re.compile(r"(?<!~)(?:IDR|Rp\.?)\s?(\d{1,3}(?:[.,]\d{3})+)")
FLOOR_LINE = re.compile(r"\b(floor|salary_floor|batas gaji)\b", re.I)
RETIRED = [
    (re.compile(r"\b5[.,]000[.,]000\b"), "retired floor IDR 5,000,000"),
    (re.compile(r"\b5\s?juta\b", re.I), "retired floor '5 juta'"),
    (re.compile(r"\b28[.,]902\b"), "retired hourly floor IDR 28,902"),
    (re.compile(r"USD\s?55[,.]?000\s?[-–]\s?65[,.]?000|USD\s?55k\s?[-–]\s?65k|~USD 55k-65k", re.I), "retired USD 55-65k underpaid benchmark"),
    (re.compile(r"Remote \((?:fully or hybrid|penuh atau hybrid)\)", re.I), "hybrid described as remote"),
]
RELOCATION_LINE = re.compile(r"\*\*Open to relocation in:\*\*(.+)")


def prose_files(root: Path = ROOT) -> list[Path]:
    out = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        if path.name in SKIP_FILES or any(part in SKIP_PARTS for part in rel.parts[:-1]):
            continue
        out.append(path)
    return sorted(out)


def _num(text: str) -> int:
    return int(re.sub(r"[.,]", "", text))


def check_text(text: str, name: str, pay: jr.PayConfig) -> list[str]:
    allowed = {round(pay.floor), round(pay.floor / pay.hours)}
    problems = []
    for n, line in enumerate(text.splitlines(), 1):
        for rx, label in RETIRED:
            if rx.search(line):
                problems.append(f"{name}:{n}: {label}")
        if FLOOR_LINE.search(line):
            for m in AMOUNT.finditer(line):
                value = _num(m.group(1))
                if value not in allowed and 1_000_000 <= value <= 50_000_000:
                    problems.append(f"{name}:{n}: floor stated as IDR {m.group(1)}, config says {round(pay.floor):,}")
        m = RELOCATION_LINE.search(line)
        if m:
            named = {jr.COUNTRY_NAMES.get(part.strip(" .;").lower()) for part in re.split(r"[,;]", m.group(1).split("(")[0])}
            named.discard(None)
            if named != set(pay.relocation):
                problems.append(f"{name}:{n}: relocation countries {sorted(named)} differ from the config {sorted(pay.relocation)}")
    return problems


def check(root: Path = ROOT, pay: jr.PayConfig | None = None) -> list[str]:
    pay = pay or jr.PAY
    problems = []
    for path in prose_files(root):
        problems += check_text(path.read_text(encoding="utf-8"), str(path.relative_to(root)), pay)
    return problems


def main() -> int:
    problems = check()
    print(json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
