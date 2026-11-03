#!/usr/bin/env python3
"""Web search with fallback: Tavily first, Brave only as the last resort.

    python tools/search_router.py search --query 'site:contra.com/opportunity flutter' [--limit 10]
    python tools/search_router.py status

Order: Tavily (monthly cap, default 1500) -> Brave (monthly cap, default 1000).
A provider is skipped when its cap is reached, its key is missing, or the call
fails (quota/HTTP error). Output is one JSON object:
{"provider": "tavily|brave", "results": [{"title", "url", "snippet"}]}.
Exit 3 when every provider is exhausted. Firecrawl is not here: only the model
can call it (MCP), see connector_sources.py fc-check.

Env: TAVILY_API_KEY, BRAVE_SEARCH_API_TOKEN, TAVILY_MONTHLY_CAP, BRAVE_MONTHLY_CAP.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tavily_search as tv  # noqa: E402

BRAVE_STATE = tv.ROOT / "job_scraper" / "brave_state.json"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
BRAVE_DEFAULT_CAP = 1000


def brave_cap() -> int:
    try:
        return int(os.environ.get("BRAVE_MONTHLY_CAP", BRAVE_DEFAULT_CAP))
    except ValueError:
        return BRAVE_DEFAULT_CAP


def brave_search(query: str, limit: int) -> list[dict]:
    key = os.environ.get("BRAVE_SEARCH_API_TOKEN")
    if not key:
        raise ValueError("BRAVE_SEARCH_API_TOKEN is not set")
    url = f"{BRAVE_API}?{urllib.parse.urlencode({'q': query, 'count': min(limit, 20)})}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Brave HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ValueError(f"Brave unreachable: {exc.reason}") from None
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")} for r in (data.get("web") or {}).get("results", [])]


def tavily_results(query: str, limit: int) -> list[dict]:
    data = tv.search(query, limit)
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")} for r in data.get("results", [])]


def route(query: str, limit: int = 10, *, tavily_state: Path = tv.STATE, brave_state: Path = BRAVE_STATE) -> dict:
    """Try each provider in order. Returns {provider, results} or {provider: None, errors}."""
    errors: list[str] = []
    providers = (
        ("tavily", tavily_state, tv.cap, tavily_results, "TAVILY_API_KEY"),
        ("brave", brave_state, brave_cap, brave_search, "BRAVE_SEARCH_API_TOKEN"),
    )
    for name, state, cap_fn, fn, env in providers:
        if not os.environ.get(env):
            errors.append(f"{name}: {env} not set")
            continue
        slot = tv.reserve(state, cap_fn())
        if not slot["allowed"]:
            errors.append(f"{name}: monthly cap {slot['cap']} reached")
            continue
        try:
            return {"provider": name, "hits": slot["hits"], "cap": slot["cap"], "results": fn(query, limit)}
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    return {"provider": None, "errors": errors, "results": []}


def status() -> dict:
    t, b = tv.load(tv.STATE), tv.load(BRAVE_STATE)
    return {"month": t["month"],
            "tavily": {"hits": t["hits"], "cap": tv.cap()},
            "brave": {"hits": b["hits"], "cap": brave_cap()}}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Search with Tavily, then Brave")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("search")
    s.add_argument("--query", required=True)
    s.add_argument("--limit", type=int, default=10)
    args = p.parse_args(argv)
    if args.cmd == "status":
        print(json.dumps(status()))
        return 0
    out = route(args.query, args.limit)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["provider"] else 3


if __name__ == "__main__":
    sys.exit(main())
