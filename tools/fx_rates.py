#!/usr/bin/env python3
"""Exchange rates to IDR for the salary-floor rule, cached once per day.

Run from the repo root:
    python tools/fx_rates.py show              # use the cache, refresh at most once a day
    python tools/fx_rates.py show --offline    # never fetch; cache only
    python tools/fx_rates.py convert 3000 SGD  # IDR value of an amount

Source: ExchangeRate-API's open-access endpoint (free, no key, daily updates,
attribution "Rates By Exchange Rate API" - https://www.exchangerate-api.com/docs/free).
Default URL https://open.er-api.com/v6/latest/IDR; override with FX_API_URL
(same response shape: {"result": "success", "base_code": "IDR",
"time_last_update_utc": ..., "rates": {"USD": 0.000061, ...}}).

Cache: job_scraper/fx_rates.json (gitignored), holding the rates, the date
they were fetched and the source. Policy, from the hard rules:
- refresh at most once per calendar day;
- if a refresh fails, use the last cached rates and mark them stale;
- with no cache and no fetch, there is no rate - callers must mark the job
  needs_salary_verification. A rate is never guessed.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = ROOT / "job_scraper" / "fx_rates.json"
DEFAULT_URL = "https://open.er-api.com/v6/latest/IDR"
USER_AGENT = "ai-job-search fx_rates/1.0"


@dataclass
class FxTable:
    """Rates as units of currency per 1 IDR, as the API publishes them."""

    rates: dict[str, float]
    fetched_on: str  # YYYY-MM-DD the rates were fetched
    source: str
    stale: bool = False  # True when a refresh failed and the cache stood in

    def idr_per_unit(self, currency: str | None) -> float | None:
        """IDR value of one unit of `currency`, or None when unknown."""
        if not currency:
            return None
        code = currency.strip().upper()
        if code == "IDR":
            return 1.0
        per_idr = self.rates.get(code)
        if not isinstance(per_idr, (int, float)) or per_idr <= 0:
            return None
        return 1.0 / per_idr


def fetch_rates(url: str | None = None, timeout: float = 15.0) -> dict:
    """GET the rate table. Raises on any network or format problem."""
    target = url or os.environ.get("FX_API_URL") or DEFAULT_URL
    if not target.startswith(("https://", "http://")):
        raise ValueError("FX_API_URL must be an http(s) URL")
    req = urllib.request.Request(target, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL scheme checked above
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("result") not in (None, "success") or not isinstance(body.get("rates"), dict):
        raise ValueError("rate API returned no rates")
    if str(body.get("base_code", "IDR")).upper() != "IDR":
        raise ValueError("rate API base must be IDR")
    return {"rates": body["rates"], "source": target, "provider_updated": body.get("time_last_update_utc")}


def read_cache(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("rates"), dict) or not data.get("fetched_on"):
        return None
    return data


def write_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_rates(
    cache_path: Path = DEFAULT_CACHE,
    today: date | None = None,
    *,
    offline: bool = False,
    fetcher: Callable[[], dict] | None = None,
) -> FxTable | None:
    """Today's rates: from the cache if fetched today, else fetched (and cached).

    A failed fetch falls back to the cache marked stale; no cache -> None.
    """
    today = today or date.today()
    cached = read_cache(cache_path)
    if cached and cached["fetched_on"] == today.isoformat():
        return FxTable(cached["rates"], cached["fetched_on"], cached.get("source", "cache"))
    if not offline:
        try:
            fresh = (fetcher or fetch_rates)()
            payload = {
                "fetched_on": today.isoformat(),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **fresh,
            }
            write_cache(cache_path, payload)
            return FxTable(payload["rates"], payload["fetched_on"], payload.get("source", ""))
        except Exception:  # noqa: BLE001 - any failure means "fall back to the cache"
            pass
    if cached:
        return FxTable(cached["rates"], cached["fetched_on"], cached.get("source", "cache"), stale=cached["fetched_on"] != today.isoformat())
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exchange rates to IDR (cached daily)")
    parser.add_argument("command", choices=["show", "convert"])
    parser.add_argument("amount", nargs="?", type=float)
    parser.add_argument("currency", nargs="?")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true", help="never fetch; use the cache only")
    args = parser.parse_args(argv)
    table = load_rates(args.cache, offline=args.offline)
    if table is None:
        print(json.dumps({"error": "no exchange rates: fetch failed and no cache", "code": "NO_FX"}), file=sys.stderr)
        return 1
    if args.command == "show":
        picks = ["USD", "SGD", "EUR", "GBP", "AUD", "JPY", "KRW", "MYR", "INR", "PHP", "THB", "VND"]
        print(json.dumps({"fetched_on": table.fetched_on, "stale": table.stale, "source": table.source,
                          "idr_per_unit": {c: round(table.idr_per_unit(c) or 0, 4) for c in picks}}, indent=2))
        return 0
    if args.amount is None or not args.currency:
        parser.error("convert needs AMOUNT CURRENCY")
    rate = table.idr_per_unit(args.currency)
    if rate is None:
        print(json.dumps({"error": f"no rate for {args.currency}", "code": "NO_FX"}), file=sys.stderr)
        return 1
    print(json.dumps({"idr": round(args.amount * rate, 2), "fx_rate": rate, "fx_date": table.fetched_on, "stale": table.stale}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
