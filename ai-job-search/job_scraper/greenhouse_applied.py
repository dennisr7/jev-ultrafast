#!/usr/bin/env python3
"""
Lists the jobs you have applied to through MyGreenhouse and marks them in seen_jobs.json.

Reads the same data the MyGreenhouse Applications page loads (my.greenhouse.io/applications.json),
from a background tab of your own Chrome through Browser Harness (the connection Jev uses).
You must be signed in to MyGreenhouse in Chrome, with remote debugging enabled
(chrome://inspect/#remote-debugging). Read-only: it only fetches your application list.

Outputs:
  applications/greenhouse_applied.csv   every application: applied_at, company, title,
                                        active/inactive, job post URL and id
  applications/manual_applied.csv       (input) applications made while signed out of MyGreenhouse;
                                        merged into the output with source "manual"
  job_scraper/seen_jobs.json            tracked jobs you applied to get status "applied" and
                                        applied_date (matched by Greenhouse job id, else by
                                        company + title); export_all_jobs.py then drops them
                                        from applications/all_jobs.csv

Usage (needs Jev's environment for browser_harness):
  cd jev-ultrafast && uv run python ../job_scraper/greenhouse_applied.py [--dry-run]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "jev-ultrafast"))
from jev_ultrafast.browser import Browser  # noqa: E402

SEEN_JOBS_PATH = os.path.join(ROOT, "job_scraper", "seen_jobs.json")
OUTPUT_PATH = os.path.join(ROOT, "applications", "greenhouse_applied.csv")
# Applications MyGreenhouse can't see (e.g. submitted while signed out). Same columns as the output, plus note.
MANUAL_PATH = os.path.join(ROOT, "applications", "manual_applied.csv")
EXPORT_SCRIPT = os.path.join(ROOT, "job_scraper", "export_all_jobs.py")
URL = "https://my.greenhouse.io/applications"
FIELDS = ["applied_at", "company", "title", "state", "locations", "job_post_url", "job_post_id", "application_id",
          "source", "note"]

# Page through applications.json for active and all applications; return only the fields we keep.
FETCH = r"""(async () => {
  const out = new Map();
  for (const active of ['true', 'false']) {
    for (let page = 1; page <= 50; page++) {
      const r = await fetch(`/applications.json?page=${page}&active_only=${active}`,
        {headers: {Accept: 'application/json'}, credentials: 'same-origin'});
      if (!r.ok) return {error: `HTTP ${r.status} on page ${page}`};
      const body = await r.json();
      const group = body.active || body.inactive || body.all || Object.values(body).find(v => v && v.applications);
      const apps = group?.applications || [];
      for (const a of apps) out.set(a.id, {
        application_id: a.id, company: a.company_name, title: a.job_title, locations: a.locations,
        job_post_url: a.job_post_url, job_post_id: a.job_post_id, applied_at: a.applied_at,
        state: a.inactive ? 'inactive' : 'active'});
      if (!apps.length || page >= (group?.total_pages || 1)) break;
    }
  }
  return {apps: [...out.values()]};
})()"""


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def greenhouse_id(url):
    m = re.search(r"(?:gh_jid=|/jobs/)(\d{6,})", url or "")
    return m.group(1) if m else None


def fetch_applications():
    browser = Browser(URL)
    try:
        if "my.greenhouse.io" not in (browser.evaluate("location.href") or ""):
            sys.exit("MyGreenhouse redirected away; sign in to it in Chrome and run again.")
        # Start the fetch without awaiting it (Browser Harness calls time out after 5s), then poll.
        browser.evaluate(f"window.__ghApplied = null; {FETCH}.then(r => window.__ghApplied = r, "
                         "e => window.__ghApplied = {error: String(e)}); true")
        result = None
        for _ in range(240):
            result = browser.evaluate("window.__ghApplied")
            if result:
                break
            time.sleep(0.5)
    finally:
        browser.close()
    result = result or {"error": "timed out after 2 minutes"}
    if "error" in result or "apps" not in result:
        sys.exit(f"Could not read applications.json ({result.get('error', 'no data')}). "
                 "Check that you are signed in to MyGreenhouse in Chrome.")
    return sorted(result["apps"], key=lambda a: a["applied_at"] or "", reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry-run", action="store_true", help="Print the list and matches; write nothing.")
    args = parser.parse_args()

    apps = [dict(a, source="mygreenhouse", note="") for a in fetch_applications()]
    if os.path.exists(MANUAL_PATH):
        with open(MANUAL_PATH, newline="") as f:
            apps += [dict(row, source="manual") for row in csv.DictReader(f)]
    apps.sort(key=lambda a: a["applied_at"] or "", reverse=True)

    with open(SEEN_JOBS_PATH) as f:
        data = json.load(f)
    seen = data.get("seen", data)
    by_id, by_name = {}, {}
    for url, job in seen.items():
        if gid := greenhouse_id(url):
            by_id.setdefault(gid, []).append(url)
        by_name.setdefault((norm(job.get("company")), norm(job.get("title"))), []).append(url)

    marked = []
    for app in apps:
        urls = by_id.get(str(app["job_post_id"])) or by_name.get((norm(app["company"]), norm(app["title"])), [])
        for url in urls:
            job = seen[url]
            date = (app["applied_at"] or "")[:10]
            if job.get("status") != "applied" or date > job.get("applied_date", ""):
                marked.append((job.get("status"), app["company"], app["title"]))
                if not args.dry_run:
                    job["status"] = "applied"
                    job["applied_date"] = date

    for app in apps:
        tag = "  (manual)" if app["source"] == "manual" else ""
        print(f"{(app['applied_at'] or '?')[:10]}  {app['state']:8}  {app['company']} | {app['title'].strip()}{tag}")
    print(f"\n{len(apps)} applications; {len(marked)} tracked job(s) newly marked applied"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    for old, company, title in marked:
        print(f"  {old} -> applied: {company} | {title.strip()}")
    if args.dry_run:
        return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: app.get(k, "") for k in FIELDS} for app in apps)
    print(f"Wrote {OUTPUT_PATH}")
    if marked:
        with open(SEEN_JOBS_PATH, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        subprocess.run([sys.executable, EXPORT_SCRIPT], check=False)


if __name__ == "__main__":
    main()
