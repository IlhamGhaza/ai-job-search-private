#!/usr/bin/env python3
"""Tavily web search with a hard monthly hit cap (default 1500).

The key comes from the TAVILY_API_KEY environment variable only; it is never
written to a file. The month's count lives in job_scraper/tavily_state.json
(git-ignored) and resets when the calendar month changes.

    python tools/tavily_search.py status
    python tools/tavily_search.py search --query 'site:contra.com/opportunity flutter' [--max-results 10] [--include-domains a.com,b.com]

`search` refuses (exit 3) once the cap is reached. Set TAVILY_MONTHLY_CAP to change it.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "job_scraper" / "tavily_state.json"
API = "https://api.tavily.com/search"
DEFAULT_CAP = 1500


def cap() -> int:
    try:
        return int(os.environ.get("TAVILY_MONTHLY_CAP", DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def load(path: Path = STATE, today: date | None = None) -> dict:
    month = (today or date.today()).strftime("%Y-%m")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if data.get("month") != month:
        data = {"month": month, "hits": 0}
    return data


def save(data: dict, path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def reserve(path: Path = STATE, limit: int | None = None, today: date | None = None) -> dict:
    """Count one hit before the call, so a crash cannot undercount. {allowed, hits, cap}."""
    limit = cap() if limit is None else limit
    data = load(path, today)
    if data["hits"] >= limit:
        return {"allowed": False, "hits": data["hits"], "cap": limit, "month": data["month"]}
    data["hits"] += 1
    save(data, path)
    return {"allowed": True, "hits": data["hits"], "cap": limit, "month": data["month"]}


def search(query: str, max_results: int = 10, include_domains: list[str] | None = None) -> dict:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY is not set")
    body = {"query": query, "max_results": max_results, "search_depth": "basic"}
    if include_domains:
        body["include_domains"] = include_domains
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Tavily HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ValueError(f"Tavily unreachable: {exc.reason}") from None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tavily search with a monthly cap")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("search")
    s.add_argument("--query", required=True)
    s.add_argument("--max-results", type=int, default=10)
    s.add_argument("--include-domains", default="")
    args = p.parse_args(argv)
    try:
        if args.cmd == "status":
            data = load()
            print(json.dumps({"month": data["month"], "hits": data["hits"], "cap": cap(), "remaining": cap() - data["hits"]}))
            return 0
        slot = reserve()
        if not slot["allowed"]:
            print(json.dumps({"error": "monthly cap reached", **slot}), file=sys.stderr)
            return 3
        domains = [d.strip() for d in args.include_domains.split(",") if d.strip()]
        print(json.dumps(search(args.query, args.max_results, domains or None), ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
