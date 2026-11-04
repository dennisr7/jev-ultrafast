#!/usr/bin/env python3
"""
Mechanical (no-LLM) filter for one company's Workday career site.

Unlike Greenhouse (one call gets every job's full description), Workday's
list endpoint only returns title/location/externalPath - no description, and
caps results at 20/page. So this is necessarily a TWO-STAGE pipeline:

  1. LIST: page through search results for a scoping query (default
     "engineer" - broad enough to catch most technical titles without
     pulling a company's entire board, which can run into the thousands).
     Apply a cheap TITLE-only seniority filter here - jobs with a strong
     seniority marker in the title are dropped before costing a detail call.
  2. DETAIL: for the survivors only, fetch the full description (one request
     each) and apply the same years-of-experience regex used by the
     Greenhouse sweep script, to catch explicit "N years" bars that a
     generic title wouldn't reveal.

This keeps the total request count proportional to plausible matches, not to
a company's total job count.

Usage:
  python3 sweep_company_workday.py <tenant> <instance> <site> [--company-name NAME]
      [--query TEXT ...] [--pages N] [--max-years N]

Output (stdout): a single JSON object:
  {
    "tenant": "...", "status": "ok" | "no_board" | "fetch_error",
    "list_scanned": <int>, "title_filtered_out": <int>,
    "matched_jobs": [ {...}, ... ], "excluded_after_detail": <int>
  }
"""
import sys
import json
import re
import argparse
import urllib.request
import urllib.error
import time

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PAGE_SIZE = 20  # Workday's own hard cap

SENIORITY_MARKERS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b", r"\bdirector\b",
    r"\bvp\b", r"\bvice president\b", r"\bchief\b", r"\bhead of\b",
    r"\blead\b(?!\s*generation)", r"\bmanager\b",
]
SENIORITY_RE = re.compile("|".join(SENIORITY_MARKERS), re.IGNORECASE)

# Same heuristic as the Greenhouse sweep script - see that file's header
# comment for the deliberate decision not to broaden this further.
YEARS_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(?:\d{1,2}\s*\+?\s*)?\s*years?\s+"
    r"(?:of\s+)?(?:[a-zA-Z][a-zA-Z/\-]*\s+){0,6}?experience",
    re.IGNORECASE,
)


def decode_entities(text: str) -> str:
    replacements = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&#39;": "'", "&apos;": "'", "&nbsp;": " ", "&mdash;": "—",
        "&ndash;": "–", "&rsquo;": "’", "&lsquo;": "‘",
        "&rdquo;": "”", "&ldquo;": "“", "&hellip;": "…",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    return text


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(raw: str) -> str:
    return strip_tags(decode_entities(raw))


def http_json(url: str, method: str = "GET", body: dict | None = None, max_retries: int = 4):
    delay = 1.0
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "User-Agent": UA,
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 422):
                return None, "not_found"
            if e.code == 429 or e.code >= 500:
                if attempt == max_retries:
                    return None, f"http_{e.code}"
                time.sleep(delay)
                delay = min(delay * 2, 8)
                continue
            return None, f"http_{e.code}"
        except Exception as e:
            if attempt == max_retries:
                return None, str(e)
            time.sleep(delay)
            delay = min(delay * 2, 8)
    return None, "max_retries_exceeded"


def estimate_min_years(text: str):
    matches = YEARS_RE.findall(text)
    if not matches:
        return None
    years = [int(m) for m in matches if m.isdigit()]
    return min(years) if years else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant")
    ap.add_argument("instance")
    ap.add_argument("site")
    ap.add_argument("--company-name", default=None)
    ap.add_argument("--query", action="append", default=None)
    ap.add_argument("--pages", type=int, default=3, help="Pages per query, 20 results/page (default 3 = 60/query)")
    ap.add_argument("--max-years", type=int, default=3)  # preference: 2-3 years, not 5
    args = ap.parse_args()

    queries = args.query or ["engineer"]
    company_name = args.company_name or args.tenant
    cxs_base = f"https://{args.tenant}.{args.instance}.myworkdayjobs.com/wday/cxs/{args.tenant}/{args.site}"
    public_base = f"https://{args.tenant}.{args.instance}.myworkdayjobs.com/{args.site}"

    # Stage 1: list + title filter, deduped by externalPath across queries.
    candidates = {}  # externalPath -> {title, location, postedOn}
    list_scanned = 0
    title_filtered_out = 0
    saw_any_response = False

    for q in queries:
        for page in range(args.pages):
            offset = page * PAGE_SIZE
            data, err = http_json(cxs_base + "/jobs", method="POST", body={
                "appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": q,
            })
            if err == "not_found" and not saw_any_response:
                print(json.dumps({"tenant": args.tenant, "status": "no_board"}))
                return
            if err is not None:
                continue  # skip this page, keep going
            saw_any_response = True
            postings = data.get("jobPostings", [])
            if not postings:
                break
            for job in postings:
                list_scanned += 1
                ext_path = job.get("externalPath")
                title = job.get("title", "")
                if not ext_path:
                    continue
                if SENIORITY_RE.search(title):
                    title_filtered_out += 1
                    continue
                candidates[ext_path] = {
                    "title": title,
                    "location": job.get("locationsText"),
                    "postedOn": job.get("postedOn"),
                }
            if len(postings) < PAGE_SIZE:
                break  # last page for this query

    if not saw_any_response:
        print(json.dumps({"tenant": args.tenant, "status": "fetch_error", "error": "no_response_any_query"}))
        return

    # Stage 2: detail fetch for survivors, apply years-of-experience filter.
    matched = []
    excluded_after_detail = 0
    for ext_path, meta in candidates.items():
        detail, err = http_json(cxs_base + ext_path)
        if err is not None or not detail:
            continue
        info = detail.get("jobPostingInfo", {})
        description = clean_text(info.get("jobDescription", "") or "")
        combined = f"{meta['title']} {description}"
        min_years = estimate_min_years(combined)

        if min_years is not None and min_years > args.max_years:
            excluded_after_detail += 1
            continue

        matched.append({
            "id": info.get("jobReqId") or info.get("id"),
            "title": meta["title"],
            "company": company_name,
            "location": info.get("location") or meta.get("location"),
            "url": f"{public_base}{ext_path}",
            "first_published": info.get("startDate") or meta.get("postedOn"),
            "estimated_min_years": min_years,
            "inclusion_reason": f"stated_min_years={min_years}" if min_years is not None else "no_years_stated_no_seniority_marker",
            # Already downloaded during the detail fetch above - stashing it
            # here lets /rank score straight from this text instead of
            # re-fetching the same posting with WebFetch.
            "description": description,
        })

    print(json.dumps({
        "tenant": args.tenant,
        "status": "ok",
        "list_scanned": list_scanned,
        "title_filtered_out": title_filtered_out,
        "matched_jobs": matched,
        "excluded_after_detail": excluded_after_detail,
    }))


if __name__ == "__main__":
    main()
