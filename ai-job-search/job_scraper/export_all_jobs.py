#!/usr/bin/env python3
"""
Regenerates applications/all_jobs.csv from job_scraper/seen_jobs.json.

This is the "numbers game" export for browser-based (Claude in Chrome)
application sessions - every job with status "new" or "ranked" (skipped and
expired entries are excluded). Ranked jobs are sorted first, by score
descending, so /rank's judgment is reflected even in the unfiltered export;
unranked "new" jobs follow, grouped by company.

Called automatically at the end of /greenhouse-sweep, /workday-sweep, and
/rank (any skill that changes seen_jobs.json's status/rank fields), so
applications/all_jobs.csv never goes stale relative to seen_jobs.json.

Usage:
  python3 job_scraper/export_all_jobs.py

Output: overwrites applications/all_jobs.csv. Prints a one-line summary to
stdout (row count by status) for the calling skill to relay to the user.
"""
import json
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN_JOBS_PATH = os.path.join(ROOT, "job_scraper", "seen_jobs.json")
OUTPUT_PATH = os.path.join(ROOT, "applications", "all_jobs.csv")

FIELDNAMES = [
    "title", "company", "rank_score", "rank_verdict", "location_flag",
    "employment_type", "estimated_min_years", "status", "source",
    "first_seen", "url",
]


def sort_key(row):
    if row["status"] == "ranked" and row["rank_score"] != "":
        return (0, -float(row["rank_score"]))
    return (1, row["company"])


def main():
    with open(SEEN_JOBS_PATH) as f:
        data = json.load(f)
    seen = data.get("seen", data) if isinstance(data, dict) else data

    rows = []
    for url, v in seen.items():
        if v.get("status") not in ("new", "ranked"):
            continue
        rows.append({
            "title": v.get("title", ""),
            "company": v.get("company", ""),
            "rank_score": v.get("rank_score", ""),
            "rank_verdict": v.get("rank_verdict", ""),
            "location_flag": v.get("location_flag", ""),
            "employment_type": v.get("employment_type", ""),
            "estimated_min_years": v.get("estimated_min_years", ""),
            "status": v.get("status"),
            "source": v.get("source", ""),
            "first_seen": v.get("first_seen", ""),
            "url": url,
        })

    rows.sort(key=sort_key)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)

    ranked = sum(1 for r in rows if r["status"] == "ranked")
    new = sum(1 for r in rows if r["status"] == "new")
    print(f"applications/all_jobs.csv: {len(rows)} rows ({ranked} ranked, {new} new/unranked)")


if __name__ == "__main__":
    main()
