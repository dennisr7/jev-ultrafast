#!/usr/bin/env python3
"""
Mechanical (no-LLM) filter for one company's Greenhouse job board.

Fetches https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true
(a single request returns every open job AND its full description for that
company), regex-extracts "years of experience" style requirements from each
job's title + description, and keeps jobs whose estimated minimum requirement
is <=5 years (or where no year requirement is stated and the title has no
strong seniority marker).

This is intentionally mechanical, not LLM-based: the year-extraction regex is
a heuristic, not a guarantee of accuracy. Treat "estimated_min_years" as a
triage signal, not ground truth - always read the actual posting before
deciding to apply. That's exactly the same caveat /rank and /apply already
apply to any quick/triage signal in this repo.

Usage:
  python3 sweep_company.py <greenhouse_token> [--max-years N]

Output (stdout): a single JSON object:
  {
    "token": "...",
    "status": "ok" | "no_board" | "fetch_error",
    "total_jobs": <int>,
    "matched_jobs": [ {...}, ... ],
    "excluded_count": <int>
  }
On fetch_error, an "error" field is included.
"""
import sys
import json
import re
import urllib.request
import urllib.error
import time

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SENIORITY_MARKERS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b", r"\bdirector\b",
    r"\bvp\b", r"\bvice president\b", r"\bchief\b", r"\bhead of\b",
    r"\blead\b(?!\s*generation)",  # avoid matching "lead generation"
]
SENIORITY_RE = re.compile("|".join(SENIORITY_MARKERS), re.IGNORECASE)

# Title-level relevance gate, added 2026-09-22 after a real sweep (Anduril,
# Anthropic) flooded seen_jobs.json with Sales/CS/Recruiting roles that
# technically passed the years/seniority filter (e.g. "Enterprise Account
# Executive" with no stated years requirement). A company's Greenhouse board
# spans every department, not just engineering - this narrows to titles that
# plausibly match the candidate's technical domains (cybersecurity, agentic
# AI/ML, embedded/hardware, VR/AR, HCI/UX, power/energy engineering, general
# SWE) before years/seniority logic ever runs. Mirrors workday-sweep's
# --query "engineer" default scoping, applied as a title filter instead since
# Greenhouse's list endpoint has no server-side search param to pre-scope with.
RELEVANT_TITLE_MARKERS = [
    r"\bengineer(ing)?\b", r"\bdeveloper\b", r"\bprogrammer\b",
    r"\bfirmware\b", r"\bembedded\b", r"\bhardware\b", r"\bsoftware\b",
    r"\bsecurity\b", r"\bcyber\b", r"\bpenetration\b", r"\bsoc\b",
    r"\bincident response\b", r"\bdata (scientist|engineer|analyst)\b",
    r"\bmachine learning\b", r"\bml\b", r"\bartificial intelligence\b",
    r"\bresearch(er)?\b", r"\bscientist\b", r"\bsystems?\b", r"\bnetwork\b",
    r"\bdevops\b", r"\binfrastructure\b", r"\bcloud\b", r"\bplatform\b",
    r"\bbackend\b", r"\bfrontend\b", r"\bfull[- ]?stack\b", r"\bux\b", r"\bui\b",
    r"\bhuman factors\b", r"\busability\b", r"\btechnician\b",
    r"\bquality assurance\b", r"\bqa\b", r"\btest(er|ing)?\b", r"\biot\b",
    r"\brobotics\b", r"\bautomation\b", r"\bcontrols?\b", r"\belectrical\b",
    r"\bmechanical\b", r"\bpower systems?\b", r"\benergy\b", r"\brf\b",
    r"\bwireless\b", r"\bvirtual reality\b", r"\baugmented reality\b", r"\bvr\b",
    r"\bapplication security\b", r"\bproduct security\b",
]
RELEVANT_TITLE_RE = re.compile("|".join(RELEVANT_TITLE_MARKERS), re.IGNORECASE)

# "Sales Engineer" / "Solutions Engineer" (pre-sales/GTM roles, not technical
# build roles) contain "engineer" and pass RELEVANT_TITLE_RE despite being
# fundamentally sales positions. Excluded explicitly rather than trying to
# make the positive keyword list smart enough to tell them apart.
IRRELEVANT_TITLE_OVERRIDE_RE = re.compile(
    r"\bsales engineer\b|\bsolutions? engineer\b", re.IGNORECASE
)

# Matches patterns like "5+ years", "3-5 years", "minimum of 4 years",
# "at least 2 years of experience", "5+ years of software engineering
# experience", "1+ years of firmware or embedded software development
# experience". Captures the first (lower-bound) number. The (?:of\s+)?
# (?:\w+\s+){0,6}? span allows an arbitrary short domain descriptor between
# "of" and "experience" (postings rarely just say "years of experience" -
# they qualify what kind), matched non-greedily so it stops at the nearest
# "experience" rather than swallowing past it.
#
# KNOWN GAP (deliberately not fixed - see conversation 2026-09-22): this only
# catches "N years ... experience" phrasing, not "N years in/as/building/
# leading X" phrasing that skips the word "experience" (e.g. a posting's
# *preferred* quals saying "5+ years in operations engineering, RevOps, or a
# similar role"). Such phrasing falls through to the no-years-stated path
# below. Broadening the regex to catch "years in/as/building/..." was
# considered and rejected: it would also match boilerplate like "we've been
# operating for 15 years in the industry" and wrongly exclude a genuinely
# entry-level posting over unrelated company-history text. Given the
# candidate's explicit "cast the widest net, let /rank filter" strategy,
# under-catching (defaults to inclusion) is the safer failure direction than
# over-catching (defaults to exclusion) - so this stays as-is.
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


def clean_content(raw: str) -> str:
    return strip_tags(decode_entities(raw))


def fetch_json(url: str, max_retries: int = 4):
    delay = 1.0
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            if e.code == 429 or e.code >= 500:
                if attempt == max_retries:
                    return None, f"http_{e.code}"
                time.sleep(delay)
                delay = min(delay * 2, 8)
                continue
            return None, f"http_{e.code}"
        except Exception as e:  # network errors, timeouts
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
    if not years:
        return None
    # The lowest stated figure is usually the actual minimum bar (a posting
    # asking for "5-7 years" is really asking for 5+; "3+ years" is 3+).
    return min(years)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "fetch_error", "error": "usage: sweep_company.py <token> [--max-years N]"}))
        sys.exit(1)

    token = sys.argv[1]
    max_years = 5
    if "--max-years" in sys.argv:
        idx = sys.argv.index("--max-years")
        if idx + 1 < len(sys.argv):
            max_years = int(sys.argv[idx + 1])

    data, err = fetch_json(f"{BASE_URL}/{token}/jobs?content=true")
    if err == "not_found":
        print(json.dumps({"token": token, "status": "no_board"}))
        return
    if err is not None:
        print(json.dumps({"token": token, "status": "fetch_error", "error": err}))
        return

    jobs = data.get("jobs", [])
    matched = []
    excluded = 0
    excluded_irrelevant_title = 0

    for job in jobs:
        title = job.get("title", "")

        if not RELEVANT_TITLE_RE.search(title) or IRRELEVANT_TITLE_OVERRIDE_RE.search(title):
            excluded_irrelevant_title += 1
            continue

        content_raw = job.get("content", "") or ""
        content = clean_content(content_raw)
        combined = f"{title} {content}"

        min_years = estimate_min_years(combined)
        has_seniority_marker = bool(SENIORITY_RE.search(title))

        if min_years is not None:
            include = min_years <= max_years
            reason = f"stated_min_years={min_years}"
        elif has_seniority_marker:
            include = False
            reason = "title_seniority_marker_no_years_stated"
        else:
            include = True
            reason = "no_years_stated_no_seniority_marker"

        if not include:
            excluded += 1
            continue

        location = job.get("location") or {}
        matched.append({
            "id": str(job.get("id")),
            "title": title,
            "company": job.get("company_name"),
            "location": location.get("name"),
            "url": job.get("absolute_url"),
            "first_published": job.get("first_published"),
            "estimated_min_years": min_years,
            "title_seniority_marker": has_seniority_marker,
            "inclusion_reason": reason,
            # Already downloaded via ?content=true - stashing it here lets
            # /rank score straight from this text instead of re-fetching the
            # same posting with WebFetch.
            "description": content,
        })

    print(json.dumps({
        "token": token,
        "status": "ok",
        "total_jobs": len(jobs),
        "matched_jobs": matched,
        "excluded_count": excluded,
        "excluded_irrelevant_title": excluded_irrelevant_title,
    }))


if __name__ == "__main__":
    main()
