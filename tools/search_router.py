#!/usr/bin/env python3
"""Web search with fallback: Firecrawl keys first, then Tavily, Brave last.

    python tools/search_router.py search --query 'site:contra.com/opportunity flutter' [--limit 10]
    python tools/search_router.py status

Order: every Firecrawl key (FIRECRAWL_API_KEY, FIRECRAWL_API_KEY_1, _2, ...) in turn
-> Tavily (monthly cap, default 1500) -> Brave (monthly cap, default 1000).
A Firecrawl key that answers 401/402/403 is parked until the next UTC day
(job_scraper/firecrawl_state.json holds env-var names only, never keys) and the
next key is tried. A provider is skipped when its cap is reached, its key is
missing, or the call fails (quota/HTTP error). Output is one JSON object:
{"provider": "tavily|brave", "results": [{"title", "url", "snippet"}]}.
Exit 3 when every provider is exhausted. Firecrawl is not here: only the model
can call it (MCP), see connector_sources.py fc-check.

Env: FIRECRAWL_API_KEY[_N], TAVILY_API_KEY, BRAVE_SEARCH_API_TOKEN, TAVILY_MONTHLY_CAP, BRAVE_MONTHLY_CAP.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tavily_search as tv  # noqa: E402

BRAVE_STATE = tv.ROOT / "job_scraper" / "brave_state.json"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
BRAVE_DEFAULT_CAP = 1000
FIRECRAWL_STATE = tv.ROOT / "job_scraper" / "firecrawl_state.json"
FIRECRAWL_API = "https://api.firecrawl.dev/v1/search"
FIRECRAWL_PARK = (401, 402, 403)  # bad key or out of credits: skip this key for the rest of the UTC day


def firecrawl_key_names() -> list[str]:
    """Env var names holding Firecrawl keys: FIRECRAWL_API_KEY, then FIRECRAWL_API_KEY_<n> in numeric order."""
    names = [n for n in os.environ if re.fullmatch(r"FIRECRAWL_API_KEY(_\d+)?", n) and os.environ[n].strip()]
    return sorted(names, key=lambda n: int(n.rsplit("_", 1)[1]) if n[-1].isdigit() else 0)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parked(path: Path = FIRECRAWL_STATE) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(data.get("parked", [])) if data.get("day") == _today() else set()


def park(name: str, path: Path = FIRECRAWL_STATE) -> None:
    names = parked(path) | {name}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"day": _today(), "parked": sorted(names)}), encoding="utf-8")


class KeyParked(ValueError):
    """The Firecrawl key is out of credits or rejected."""


def firecrawl_search(query: str, limit: int, key: str) -> list[dict]:
    body = json.dumps({"query": query, "limit": min(limit, 20)}).encode()
    req = urllib.request.Request(FIRECRAWL_API, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in FIRECRAWL_PARK:
            raise KeyParked(f"Firecrawl HTTP {exc.code}") from None
        raise ValueError(f"Firecrawl HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ValueError(f"Firecrawl unreachable: {exc.reason}") from None
    rows = data.get("data") or []
    rows = rows.get("web", []) if isinstance(rows, dict) else rows
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description") or r.get("markdown")} for r in rows]


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


def route(query: str, limit: int = 10, *, tavily_state: Path = tv.STATE, brave_state: Path = BRAVE_STATE,
          firecrawl_state: Path = FIRECRAWL_STATE) -> dict:
    """Try each provider in order. Returns {provider, results} or {provider: None, errors}."""
    errors: list[str] = []
    skip = parked(firecrawl_state)
    for env in firecrawl_key_names():
        if env in skip:
            errors.append(f"firecrawl {env}: parked until tomorrow (UTC)")
            continue
        try:
            return {"provider": "firecrawl", "key": env, "results": firecrawl_search(query, limit, os.environ[env].strip())}
        except KeyParked as exc:
            park(env, firecrawl_state)
            errors.append(f"firecrawl {env}: {exc}, parked")
        except ValueError as exc:
            errors.append(f"firecrawl {env}: {exc}")
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
            "firecrawl": {"keys": firecrawl_key_names(), "parked": sorted(parked())},
            "tavily": {"hits": t["hits"], "cap": tv.cap()},
            "brave": {"hits": b["hits"], "cap": brave_cap()}}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Search with Firecrawl keys, then Tavily, then Brave")
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
