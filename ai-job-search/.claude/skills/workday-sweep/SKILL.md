---
name: workday-sweep
description: >
  Sweeps companies in company_targets.csv for a public Workday career site,
  and mechanically filters postings down to roles requiring 3 years of
  experience or less. The second-tier fallback after /greenhouse-sweep - run
  it on companies /greenhouse-sweep marked no_board, since many large
  companies use Workday instead of Greenhouse. Feeds results into the same
  job_scraper/seen_jobs.json used by /scrape, so /rank can score them
  afterward. Trigger phrases: workday sweep, sweep workday companies,
  /workday-sweep
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(python3 .claude/skills/workday-sweep/sweep_company_workday.py *), Bash(python3 job_scraper/export_all_jobs.py), WebSearch, Agent
---

# Workday Sweep

The second tier of the company-sweep fallback chain: **Greenhouse first
(`/greenhouse-sweep`), then Workday (this skill), then raw HTML scraping**
as a last resort for companies neither of those API-based sweeps can reach.

Runs `company_targets.csv` through Workday's public candidate-search API,
company by company, and keeps postings whose experience requirement is **3
years or less** (preference: aim at 2-3 years, not 5). Same wide-net, mechanical-filter philosophy as
`/greenhouse-sweep` - **not fit judgment**. Run `/rank` afterward on results.

## Why this exists as a separate skill from /greenhouse-sweep

Workday's API shape is meaningfully different, not just a different token:

- **Three-part coordinates**, not one token: `tenant` + `instance` (`wd1`,
  `wd5`, ...) + `site` name. All three must be resolved before a company can
  be swept.
- **No bulk description fetch.** Greenhouse's `?content=true` returns every
  job's full text in one call; Workday's list endpoint never includes
  descriptions, and years-of-experience filtering needs the description. So
  this sweep is a **two-stage pipeline** per company: list + cheap title
  filter, then detail-fetch only the survivors. See Design Notes.
- **Not every large company is reachable this way either.** Some companies
  (Apple, confirmed) run Workday fully server-side with no public API at all
  — those need the raw-HTML-scraping tier instead, not this skill.

## Invocation

- `/workday-sweep` — process the next batch of 25 companies with
  `workday_status == pending` **and** `greenhouse_status == no_board`
  (i.e. companies Greenhouse already ruled out — this skill is the fallback,
  so it doesn't re-check companies `/greenhouse-sweep` hasn't gotten to yet)
- `/workday-sweep --batch <N>` — different batch size for this run
- `/workday-sweep --all-pending` — also include companies whose
  `greenhouse_status` is still `pending` (skip the "Greenhouse first" default
  ordering — useful if you specifically want Workday coverage now)
- `/workday-sweep --recheck` — retry companies previously marked `no_board`
  on `workday_status`
- `/workday-sweep --company "<name>"` — sweep one specific company by name

---

## Step 0: Load State

1. Read `company_targets.csv`. If it doesn't exist, tell the user to run
   `/target-companies` first and stop.
2. Read `job_scraper/seen_jobs.json` (create with `{"seen": {}}` if missing).
3. Select the batch (this skill only ever reads/writes the `workday_*`
   columns — `greenhouse_token`/`greenhouse_status` belong to
   `/greenhouse-sweep` and are never touched here):
   - Default: the next N rows (batch size from `--batch`, default 25) with
     `workday_status == pending` AND `greenhouse_status == no_board`.
   - `--all-pending`: drop the `greenhouse_status == no_board` requirement.
   - `--recheck`: the next N rows with `workday_status == no_board`.
   - `--company "<name>"`: just that one row.
4. If no rows match, say so plainly and suggest `/greenhouse-sweep` (to
   produce more `no_board` candidates) or `--all-pending`.

State the batch before proceeding.

## Step 1: Resolve Workday Coordinates

For companies in the batch without existing `workday_tenant`/`workday_instance`/
`workday_site` values, resolve them. **Use subagents on a cheap/fast model** —
pure lookup-and-extract:

- Dispatch parallel `general-purpose` agents (`model: "haiku"`), ~5 companies
  per agent.
- Each agent's job, per company: run `WebSearch` for
  `site:myworkdayjobs.com "<company name>"`. If a result URL matches
  `https?://([^.]+)\.([^.]+)\.myworkdayjobs\.com/([^/]+)`, extract
  `tenant`/`instance`/`site` from groups 1-3. If no matching result, report
  `null` (not on Workday this way — possibly hidden like Apple, possibly on a
  different ATS entirely).
- Agents must verify each found coordinate with a POST to
  `https://<tenant>.<instance>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` **with both
  `Content-Type: application/json` and `Accept: application/json` headers** (body
  `{"appliedFacets":{},"limit":1,"offset":0,"searchText":""}`) and a `total` > 0 in the reply. Without
  the Accept header Workday returns an empty body, which made agents report real boards as missing
  (2026-10-15: Northrop, Leidos, GDIT, Silicon Labs). A board that answers with `total: 0` (Qualcomm)
  has moved off Workday: mark it `no_board`.
- Agents return: `[{"company": "...", "tenant": "..." | null, "instance": "..." | null, "site": "..." | null}]`.

Companies with no coordinates found get `workday_status = no_board` in Step 4
and are skipped in Step 2 — these are now candidates for the raw-HTML-scraping
tier (not yet built; flag them in the summary).

## Step 2: Run the Mechanical Filter

For each company with resolved coordinates, run:

```bash
python3 .claude/skills/workday-sweep/sweep_company_workday.py <tenant> <instance> <site> --company-name "<Display Name>" \
  --query "new grad" --query "university graduate" --query "early career" --query "engineer" --pages 2 --max-years 3
```

Run these in parallel via Bash where possible (each is several sequential
HTTP calls internally — list pages, then one detail call per surviving
candidate — typically 5-15 seconds per company, noticeably slower than
Greenhouse's single-call sweep). Parse the JSON each call prints:

- `status: "no_board"` → resolved coordinates didn't actually work; treat as
  `no_board`.
- `status: "fetch_error"` → network/API problem on every query tried. Leave
  `workday_status` as `pending` for retry, don't mark `no_board`.
- `status: "ok"` → use `matched_jobs`. Note `list_scanned` and
  `title_filtered_out` for the summary — these show how much the cheap
  title-filter stage saved before any detail calls.

The default query is just `"engineer"` (broad, catches most technical titles
without pulling a company's entire board). Pass `--query` more than once for
additional scoping terms if a company's board is large and `"engineer"` alone
returns mostly noise (check `list_scanned` vs `matched_jobs` - a very low
match rate suggests the query needs narrowing or the company posts mostly in
non-English locales, both of which happen).

## Step 3: Merge into seen_jobs.json

Same dedup rule as `/greenhouse-sweep`: dedup key is the job's `url`, skip
existing entries and anything already in `job_search_tracker.csv`. New
entries:

```json
{
  "title": "...",
  "company": "...",
  "url": "...",
  "first_seen": "YYYY-MM-DD",
  "fit": "unscored",
  "status": "new",
  "estimated_min_years": <int or null>,
  "source": "workday-sweep",
  "description": "<cleaned posting text from the script's output>"
}
```

`description` carries the full cleaned posting text the script already
downloaded during Stage 2's detail fetch — copy it straight from the
script's `matched_jobs[].description` field. This lets `/rank` score the
job without a second network fetch of the same posting.

## Step 4: Update company_targets.csv

For every company processed this run, update only the Workday-prefixed columns:

- `workday_tenant`, `workday_instance`, `workday_site`: resolved coordinates
  (blank if none found)
- `workday_status`: `swept`, `no_board`, or unchanged `pending` (fetch_error)
- `last_swept_date`: today's date (shared column with `/greenhouse-sweep` —
  only move it forward, never backward)

Never touch `greenhouse_token`/`greenhouse_status`.

## Step 4.5: Refresh the Browser-Application Export

If any jobs were merged into `seen_jobs.json` in Step 3, regenerate the
"numbers game" export used for Claude-in-Chrome application sessions:

```bash
python3 job_scraper/export_all_jobs.py
```

This overwrites `applications/all_jobs.csv` from the current state of
`seen_jobs.json` - it's a full regeneration, not an incremental update, so
it's safe to call every run. Skip this step only if Step 3 added zero new
jobs (nothing changed, no need to regenerate).

## Step 5: Present Results

```
## Workday Sweep - YYYY-MM-DD

Processed N companies (X had a public Workday board, Y did not, Z had a fetch error).

Boards found: <list of company names>
Total postings scanned (list stage): <sum of list_scanned>
Title-filtered before detail calls: <sum of title_filtered_out>
Matched (<=3 yrs or no stated requirement + non-senior title): <count>
New to seen_jobs.json after dedup: <count>

### Sample of new matches
| Title | Company | Est. min years | Location |
|-------|---------|-----------------|----------|
| ... | ... | ... | ... |

### No Workday board found this batch (candidates for raw-HTML fallback)
<company names>

Remaining: <count> companies still eligible for /workday-sweep.
```

Then remind the user: mechanically filtered, not fit-scored — suggest
`/rank`. For companies `no_board` on **both** Greenhouse and Workday, note
they'd need a raw-HTML-scraping build to cover (not yet implemented — a
per-company effort, unlike this skill's coverage of every Workday-hosted
company at once).

---

## Important Rules

1. **Don't fetch a company's entire board.** Always scope with `--query`
   (default `"engineer"`) and a bounded `--pages` — some Workday boards run
   into the thousands, same as Greenhouse's largest, but without the
   single-call shortcut. Unscoped sweeps would mean one detail call per
   surviving job across a huge candidate pool.
2. **Never fabricate Workday coordinates.** If Step 1 can't find a real
   `myworkdayjobs.com` URL via WebSearch, the company is `no_board` — don't
   guess `tenant`/`instance`/`site` combinations.
3. **The years-of-experience filter is the same heuristic as Greenhouse's** —
   say so in every summary. See `sweep_company.py`'s header comment (the
   Greenhouse sweep script) for the full reasoning; this script's regex is
   identical by design, for consistent behavior across both sweeps.
4. **Batch discipline and idempotent state** — same as `/greenhouse-sweep`:
   respect `--batch`, never re-process `swept`/`no_board` rows without
   `--recheck`.
5. **This skill owns the Workday columns only.**

## Design Notes

- **Two-stage pipeline, not one call.** Workday's list endpoint gives
  title/location/externalPath only; getting years-of-experience signal needs
  the description, which is a separate `detail` call per job. Doing that for
  every listed job (not just survivors of a title filter) would multiply
  request count by a company's total posting count — the title-filter stage
  exists specifically to keep this proportional to plausible matches. A
  company report showing `list_scanned: 40, title_filtered_out: 19` means 19
  of 40 were dropped for free before costing a detail request.
- **Default `--query "engineer"` is broad on purpose.** Workday's `searchText`
  is fuzzy/relevance-based, not exact-match, so a single broad term catches
  most technical titles (software/firmware/hardware/security/systems/human
  factors engineer, etc.) without needing a query per candidate domain. This
  trades some precision (occasional irrelevant matches, non-English postings
  at global companies) for simplicity and speed - `/rank` catches the rest.
- **Global companies produce non-English/non-US results.** Unlike most
  Greenhouse-hosted companies (US-centric startups), large Workday-hosted
  companies (GE Vernova, Boeing) post in many countries and languages. This
  sweep doesn't filter by location or language — that's left to `/rank` and
  the candidate's own judgment, consistent with the "wide net, filter later"
  philosophy used throughout this pipeline.
- **Apple-style fully-hidden companies are out of scope here too.** This
  skill only reaches companies exposing Workday directly via a
  `myworkdayjobs.com` URL. A company with no such URL (hidden server-side,
  like Apple) needs raw HTML scraping of its own custom career site - a
  separate, per-company build, not something this generic skill can do.
