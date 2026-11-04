"""Search ByteDance's careers site (joinbytedance.com, PICO included) without a browser.

python3 job_scraper/bytedance_jobs.py PICO [--out applications/bytedance_pico.csv]

joinbytedance.com/api/... is behind Akamai bot protection, but the page itself calls this public
"supplier" endpoint on jobs.bytedance.com, which answers plain requests. One call returns every match
with its full description and requirements (pay is not included; it is only on the posting page).
"""

import argparse
import csv
import json
import urllib.request
from pathlib import Path

# jobs.bytedance.com resolves to servers in China and sometimes times out from the US (2026-10-12); TikTok's careers
# API serves the same ByteDance listings and is tried next.
APIS = [("https://jobs.bytedance.com/api/v1/public/supplier/search/job/posts", "https://joinbytedance.com"),
        ("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts", "https://lifeattiktok.com")]


def post(body):
    for url, origin in APIS:
        headers = {"Content-Type": "application/json", "accept-language": "en-US", "website-path": "en", "origin": origin}
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), headers),
                                                    timeout=20))["data"]
        except OSError:
            continue
    raise OSError("no ByteDance job API answered")


def search(keyword, page=200):
    jobs, offset = [], 0
    while True:
        body = {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [],
                "location_code_list": [], "keyword": keyword, "limit": page, "offset": offset}
        data = post(body)
        jobs += data["job_post_list"]
        offset += page
        if offset >= data["count"] or not data["job_post_list"]:
            return jobs


def row(job):
    name = lambda d: (d or {}).get("en_name") or ""
    return {
        "id": job["id"],
        "title": job["title"].strip(),
        "location": name(job["city_info"]),
        "type": name(job["recruit_type"]),
        "program": name(job["job_subject"]),
        "category": name(job["job_category"]),
        "url": f"https://joinbytedance.com/search/{job['id']}",
        "requirements": job["requirement"].strip(),
        "description": job["description"].strip(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("keyword")
    parser.add_argument("--out", help="CSV path (default applications/bytedance_<keyword>.csv)")
    args = parser.parse_args()
    out = Path(args.out or Path(__file__).resolve().parents[1] / "applications" / f"bytedance_{args.keyword.lower()}.csv")
    rows = [row(j) for j in search(args.keyword)]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} jobs -> {out}")


if __name__ == "__main__":
    main()
