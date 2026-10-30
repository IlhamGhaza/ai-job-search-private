#!/usr/bin/env python3
"""Merge one /scrape run's results across portals before tools/scrape_state.py.

Run from the repo root:
    python tools/job_dedup.py --in <run results.json> --out <merged.json>

scrape_state.py dedups against earlier runs (seen_jobs.json, tracker); this
tool dedups *within* a run, across sources, in a fixed order:

1. stable job id (portal + id)
2. canonical posting URL (tracking parameters, fragments, `www.` dropped)
3. canonical application URL
4. normalised company + title + location - only when all three are known

Matches are merged into one record that keeps every source in `also_seen_at`.
The employer's own listing is preferred as the primary record (an official ATS
or the employer's site beats a job board, a board beats a search lead), because
that is where to apply. Uncertain matches - same company and title but a
different or missing location - are NOT merged; both stay and are listed under
`possible_duplicates`. A LinkedIn post is never merged into a listing; it is
linked (`linked_listing` / `related_posts`) when the post names the listing's
company and title.

Stdlib only. Prints counts on stdout; the merged array goes to --out.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = re.compile(r"^(utm_.*|gh_src|gh_jid|lever-source|lever-origin|src|source|ref|refid|trk|trackingid|fbclid|gclid|mc_.*|_hs.*|campaign|origin)$", re.I)
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com", "smartrecruiters.com", "myworkdayjobs.com")
COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|limited|gmbh|ag|bv|b\.v|pte|pt|tbk|sdn\s+bhd|bhd|co|corp|corporation|kk|ab|as|oy|plc|sa|sas|srl)\b\.?", re.I)


def canonical_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    host = host[4:] if host.startswith("www.") else host
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if not TRACKING.match(k)))
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit(("https", host, path, query, ""))


def norm_text(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\((?:m|f|w|d|x|all genders?)(?:\s*/\s*(?:m|f|w|d|x))*\)", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def norm_company(value) -> str:
    return re.sub(r"\s+", " ", COMPANY_SUFFIX.sub(" ", norm_text(value))).strip()


def source_rank(job: dict) -> int:
    """Lower is better: where to apply."""
    if job.get("source_type") == "social_post" or job.get("verification_status") == "unverified_lead":
        return 3
    def on_ats(url) -> bool:
        host = (urlsplit(str(url or "")).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in ATS_HOSTS)

    if job.get("portal") == "ats-search" or on_ats(job.get("url")):
        return 0  # the employer's own listing
    if on_ats(job.get("apply_url")):
        return 1  # a board pointing at the employer's listing
    return 2


def merge(primary: dict, other: dict) -> None:
    seen = primary.setdefault("also_seen_at", [])
    entry = {"portal": other.get("portal"), "url": other.get("url")}
    if entry not in seen and entry["url"] != primary.get("url"):
        seen.append(entry)
    for key, value in other.items():
        if primary.get(key) in (None, "", []) and value not in (None, "", []):
            primary[key] = value  # fill gaps only; never overwrite a stated value
    for prior in other.get("also_seen_at") or []:
        if prior not in seen:
            seen.append(prior)


def dedupe(jobs: list[dict]) -> dict:
    listings = [j for j in jobs if isinstance(j, dict) and j.get("source_type") != "social_post"]
    posts = [j for j in jobs if isinstance(j, dict) and j.get("source_type") == "social_post"]
    # Best source first, so the first record seen under a key is the one to keep.
    listings.sort(key=source_rank)
    kept: list[dict] = []
    index: dict[str, dict] = {}
    duplicates = 0
    for job in listings:
        keys = []
        if job.get("portal") and job.get("id"):
            keys.append(f"id:{job['portal']}:{job['id']}")
        for field in ("url", "apply_url"):
            c = canonical_url(job.get(field))
            if c:
                keys.append(f"url:{c}")
        company, title, location = norm_company(job.get("company")), norm_text(job.get("title")), norm_text(job.get("location"))
        if company and title and location:
            keys.append(f"ctl:{company}|{title}|{location}")
        match = next((index[k] for k in keys if k in index), None)
        if match is not None:
            merge(match, job)
            duplicates += 1
            target = match
        else:
            kept.append(job)
            target = job
        for k in keys:
            index.setdefault(k, target)
    possible: list[dict] = []
    by_ct: dict[str, list[dict]] = {}
    for job in kept:
        company, title = norm_company(job.get("company")), norm_text(job.get("title"))
        if company and title:
            by_ct.setdefault(f"{company}|{title}", []).append(job)
    for group in by_ct.values():
        if len(group) > 1:
            possible.append({"company": group[0].get("company"), "title": group[0].get("title"), "urls": [g.get("url") for g in group]})
    linked = 0
    for post in posts:
        text = norm_text(f"{post.get('title', '')} {post.get('description', '')}")
        for job in kept:
            company, title = norm_company(job.get("company")), norm_text(job.get("title"))
            if company and title and f" {company} " in f" {text} " and all(w in text.split() for w in title.split() if len(w) > 2):
                post["linked_listing"] = job.get("url")
                job.setdefault("related_posts", []).append(post.get("url"))
                linked += 1
                break
    return {
        "jobs": kept + posts,
        "counts": {"input": len(jobs), "unique": len(kept) + len(posts), "duplicates": duplicates, "possible_duplicates": len(possible), "linked_posts": linked},
        "possible_duplicates": possible,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge one run's results across portals")
    parser.add_argument("--in", dest="inputs", type=Path, action="append", required=True, help="JSON array or {results: [...]}; repeatable")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    jobs: list[dict] = []
    for path in args.inputs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": f"cannot read {path}: {exc}", "code": "BAD_INPUT"}), file=sys.stderr)
            return 1
        jobs.extend(data.get("results", []) if isinstance(data, dict) else data)
    result = dedupe(jobs)
    args.out.write_text(json.dumps(result["jobs"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**result["counts"], "possible_duplicates": result["possible_duplicates"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
