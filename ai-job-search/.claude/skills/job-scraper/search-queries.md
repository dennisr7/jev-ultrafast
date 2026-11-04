# Search Queries for Job Scraper

<!-- SETUP: Customized for the candidate. Candidate is deliberately casting a wide net ("numbers game") across full-time and new-grad roles - not narrowing to one track. Full-time only by default: internships/co-ops are excluded from search unless they'd clearly pay enough for their location (e.g. a well-paid SF/NYC tech internship) - see the Employment Type Filter in 04-job-evaluation.md, which is the actual enforcement point since query text alone can't check pay. -->

## Search Sites

Primary:
- **Handshake** - student/early-career job board (candidate's primary source; check listings.handshake.com and campus postings)
- **linkedin.com/jobs** - LinkedIn job listings (no location filter - candidate is open to relocating anywhere in the US, and remote). Covered by the installed `linkedin-search` CLI under `.agents/skills/`.
- **indeed.com** - covered via WebSearch `site:indeed.com` queries only (no dedicated CLI - Indeed's `robots.txt` disallows `/jobs` and `/viewjob`, and the search page actively CAPTCHA-challenges direct requests, so `/add-portal` declined to scaffold a scraper for it)
- **ziprecruiter.com** - covered via WebSearch `site:ziprecruiter.com` queries only (no dedicated CLI - ZipRecruiter's `robots.txt` disallows everything for unnamed/generic bots, and even its few named allowlisted crawlers are blocked from `/jobs/` and `/jobs-search`, so `/add-portal` declined to scaffold a scraper for it)
- **Greenhouse-hosted company boards** - covered by the installed `greenhouse-search` CLI under `.agents/skills/`. Unlike the other portals, Greenhouse has no cross-company search - it's a public JSON API scoped to **one `--company` token per call**. See the "Greenhouse company watchlist" below for which tokens to check and what query to use for each.

Secondary (company career pages via Google):
- Direct Google searches with `site:` filters - no fixed target-company list yet, so favor broad keyword searches over specific `site:careers.<company>.com` queries until the candidate names companies to track

Note: this framework's built-in Danish job-portal CLI tools (Jobindex, Jobbank, Jobdanmark, Jobnet, Freehire) don't apply to a US-based candidate and have been removed from `.agents/skills/`. Rely on LinkedIn and Handshake site-searches instead. Consider `/add-portal` if Handshake proves worth scaffolding as a dedicated tool.

## Query Categories

Queries are grouped by priority. Candidate has no location constraints, so omit city/region filters unless the user asks to narrow. **Default to full-time and new-grad phrasing, not internships** - the candidate wants full-time roles primarily, with internships/co-ops only worth surfacing if pay would clearly cover living costs in that location (see the Employment Type Filter in `04-job-evaluation.md`). Each category below has a small internship sub-block for exactly that narrow case; don't expand it into a general internship search.

### Priority 1: Embedded Systems / Firmware / Hardware

Strongest technical direction - the candidate's paid experience, published work and project wins are in this area.

```
site:linkedin.com/jobs "embedded systems engineer" "new grad" OR "entry level"
site:linkedin.com/jobs "firmware engineer" "new grad" OR "entry level"
site:indeed.com "embedded systems engineer" "new grad" OR "entry level"
site:indeed.com "firmware engineer" "entry level"
site:ziprecruiter.com "embedded systems engineer" "new grad" OR "entry level"
"hardware engineer" "new grad" PCB firmware
"embedded software engineer" "entry level"
```
High-pay-only internship check (only surface if compensation clears the location's cost of living):
```
site:linkedin.com/jobs "embedded systems intern" OR "firmware intern"
```

### Priority 2: Agentic AI / Software Engineering

Matches the candidate's internship and project work.

```
site:linkedin.com/jobs "software engineer" "new grad" agentic OR "AI systems"
site:linkedin.com/jobs "machine learning engineer" "new grad" OR "AI engineer" "entry level"
site:indeed.com "software engineer" "new grad" Python OR "AI"
site:indeed.com "machine learning engineer" "entry level"
site:ziprecruiter.com "software engineer" "new grad" agentic OR Python
"software engineer" "new grad" Python C++
"data engineer" "entry level" "data lake" OR lakehouse
```
High-pay-only internship check:
```
site:linkedin.com/jobs "software engineer intern" OR "machine learning intern"
```

### Priority 3: HCI / UX / Human Factors

Adjacent direction the candidate is genuinely drawn to (published research and projects in this area).

```
site:linkedin.com/jobs "UX engineer" "new grad" OR "human factors engineer" "entry level"
site:indeed.com "UX engineer" "new grad" OR "human factors engineer" "entry level"
site:ziprecruiter.com "UX engineer" "new grad" OR "human factors engineer" "entry level"
"HCI researcher" "entry level" OR "research engineer"
"interaction design engineer" "new grad" prototyping
"accessibility engineer" "entry level"
```
High-pay-only internship check:
```
site:linkedin.com/jobs "UX engineer intern" OR "human factors intern"
```

### Priority 4: Broader / Wider Net

Wider net across IoT, hardware-adjacent, and general technical roles - deliberately broad per candidate's "numbers game" strategy. Also includes role types the candidate may not have considered given the profile:

```
site:linkedin.com/jobs "IoT engineer" "new grad" OR "entry level"
site:indeed.com "IoT engineer" "new grad" OR "entry level"
site:ziprecruiter.com "IoT engineer" "new grad" OR "entry level"
"hardware/software co-design" OR "prototyping engineer" "new grad"
"technical consultant" "new grad" engineering
"developer relations" OR "developer advocate" "new grad" OR "entry level"
"R&D engineer" "new grad" hardware
"patent" OR "IP" technical "new grad" engineering
```

## Greenhouse Company Watchlist

`greenhouse-search` has no cross-company search - for each token below, run `search -c <token> -q "<query>"` separately (in parallel where possible). Tokens are verified live as of 2026-09-22; if a token 404s later, check that company's careers page footer for a current Greenhouse link before dropping it.

| Company token | Relevance | Query to use |
|---|---|---|
| `anthropic` | Agentic AI (Priority 2) - direct match to candidate's agentic AI / Claude Code experience | `engineer` |
| `scaleai` | Agentic AI / ML (Priority 2) | `engineer` |
| `databricks` | Data engineering / agentic AI (Priority 2) | `engineer` |

This list is intentionally small (built during `/add-portal` setup, not a full market scan) - expand it as the candidate names companies to track, or as promising Greenhouse-hosted companies come up in other searches (e.g. company names seen in Priority 1/3 hardware/HCI results). `anduril`, `openai`, and `skydio` were checked and are **not** on this exact Greenhouse token (404) - they may use a different ATS or a different token; don't re-add them without re-verifying.

## Location Filter

Candidate has **no commute or location constraints** and is open to relocating anywhere in the US (or remote) after graduating. Do not filter results by location - surface everything and let the candidate decide, rather than pre-filtering a "numbers game" search.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
