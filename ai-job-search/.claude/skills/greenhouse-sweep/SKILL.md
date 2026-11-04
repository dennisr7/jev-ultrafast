---
name: greenhouse-sweep
description: >
  Sweeps every company in company_targets.csv for a public Greenhouse job board,
  and mechanically filters all postings down to roles requiring 5 years of
  experience or less. Processes companies in batches (not the whole list at once)
  since job volume can run into the thousands. Feeds results into the same
  job_scraper/seen_jobs.json used by /scrape, so /rank can score them afterward.
  Trigger phrases: greenhouse sweep, sweep companies, sweep jobs, /greenhouse-sweep
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(python3 .claude/skills/greenhouse-sweep/sweep_company.py *), Bash(python3 job_scraper/export_all_jobs.py), WebSearch, Agent
---

# Greenhouse Sweep

Runs `company_targets.csv` (built by `/target-companies`) through Greenhouse's
public Job Board API, company by company, and keeps every posting whose
experience requirement is **5 years or less** — not just "entry level." This is
the wide-net counterpart to `/scrape`'s curated few-company watchlist.

**This command does mechanical filtering, not fit judgment.** It has no opinion
on whether a role is a good fit — it only answers "does this company have a
public Greenhouse board, and does this specific posting ask for ≤5 years?" Run
`/rank` afterward on the results for real fit scoring against the candidate
profile.

## Invocation

- `/greenhouse-sweep` — process the next batch of 25 `pending` companies
- `/greenhouse-sweep --batch <N>` — use a different batch size for this run
- `/greenhouse-sweep --recheck` — retry companies previously marked `no_board`
  (in case a token guess was wrong, or they've since added a public board)
- `/greenhouse-sweep --company "<name>"` — sweep one specific company by name,
  bypassing batch selection (useful for testing or a company the user names
  directly)

---

## Step 0: Load State

1. Read `company_targets.csv`. If it doesn't exist, tell the user to run
   `/target-companies` first and stop.
2. Read `job_scraper/seen_jobs.json` (create with `{"seen": {}}` if missing).
3. Select the batch (this skill only ever reads/writes the `greenhouse_token`
   and `greenhouse_status` columns — `workday_*` columns belong to
   `/workday-sweep` and are never touched here):
   - Default: the next N rows (batch size from `--batch`, default 25) with
     `greenhouse_status == pending`, in file order.
   - `--recheck`: the next N rows with `greenhouse_status == no_board`.
   - `--company "<name>"`: just that one row (case-insensitive match).
4. If no rows match the selection, say so plainly (e.g. "All companies have
   been swept - run `/target-companies` to add more, or `--recheck` to retry
   no-board companies") and stop.

State the batch before proceeding: company names and count.

## Step 1: Resolve Greenhouse Tokens

For companies in the batch that don't already have a `greenhouse_token` value
in the CSV, resolve one. **Use subagents on a cheap/fast model for this** — it's
pure lookup-and-extract, not a task that needs a strong model:

- Dispatch parallel `general-purpose` agents (`model: "haiku"`), ~5 companies
  per agent.
- Each agent's job, per company: run `WebSearch` for
  `site:job-boards.greenhouse.io OR site:boards.greenhouse.io "<company name>"`,
  and if a result URL matches `(?:job-boards|boards)\.greenhouse\.io/([^/]+)`,
  extract that token. If no matching result, report `null` (not on Greenhouse,
  or not discoverable this way).
- Agents return a small JSON array: `[{"company": "...", "token": "..." | null}]`.
  Keep this prompt minimal — no profile context needed, this step doesn't
  involve fit judgment at all.

Companies where no token was found get `greenhouse_status = no_board` in Step 4
and are skipped in Step 2 — but **stay eligible for `/workday-sweep`**, which
checks its own `workday_status` column independently. A `no_board` here means
"not on Greenhouse," not "not reachable at all."

## Step 2: Run the Mechanical Filter

For each company with a resolved token, run:

```bash
python3 .claude/skills/greenhouse-sweep/sweep_company.py <token> --max-years 5
```

This is a **single HTTP request per company** (Greenhouse's `?content=true`
list endpoint returns every job's full description in one call) — run these in
parallel via Bash where possible. Parse the JSON each call prints to stdout:

- `status: "no_board"` → the resolved token didn't actually work (rare, but a
  WebSearch result can be stale); treat the company as `no_board`.
- `status: "fetch_error"` → network/API problem. Log it, don't fail the whole
  batch, and leave that company's `greenhouse_status` as `pending` so it's
  retried next run rather than silently marked `no_board`.
- `status: "ok"` → use `matched_jobs`.

The script's filter logic (for reference — you don't need to reimplement this,
just know what it means): a job is kept if (a) it states a minimum years
requirement of ≤5, or (b) it states no years requirement AND the title has no
strong seniority marker (Senior/Staff/Principal/Director/VP/Chief/Head of/Lead).
A job with no stated years but a seniority-marked title is excluded. **This is
a regex heuristic, not ground truth** — see Design Notes below.

## Step 3: Merge into seen_jobs.json

For each matched job across the batch:

- Dedup key: the job's `url`. Skip if already present in `seen_jobs.json` or
  already in `job_search_tracker.csv` (same rule as `/scrape`).
- Add new entries with:
  ```json
  {
    "title": "...",
    "company": "...",
    "url": "...",
    "first_seen": "YYYY-MM-DD",
    "fit": "unscored",
    "status": "new",
    "estimated_min_years": <int or null>,
    "source": "greenhouse-sweep",
    "description": "<cleaned posting text from the script's output>"
  }
  ```
  `fit: "unscored"` (not `high/medium/low`) marks these as mechanically
  filtered but never quality-judged — distinct from `/scrape`'s quick
  title-based fit tagging. `/rank` will pick up any `status: "new"` entry
  regardless of `fit` value, so this integrates cleanly.

  `description` carries the full cleaned posting text the script already
  downloaded via `?content=true` — copy it straight from the script's
  `matched_jobs[].description` field into the `seen_jobs.json` entry. This
  lets `/rank` score the job without a second network fetch of the same
  posting.

## Step 4: Update company_targets.csv

For every company processed this run (whether matched, no_board, or
fetch_error), update only the Greenhouse-prefixed columns:

- `greenhouse_token`: the resolved token (blank if none found)
- `greenhouse_status`: `swept` (had a board, processed successfully),
  `no_board` (no Greenhouse presence found), or unchanged/`pending`
  (fetch_error — retry later)
- `last_swept_date`: today's date (only for `swept` or `no_board`, not for
  `fetch_error`) — this column is shared with `/workday-sweep`, so only
  overwrite it when it moves later than what's already there, never backward.

Write the file back in place - don't reorder or drop rows, and never touch
`workday_tenant`/`workday_instance`/`workday_site`/`workday_status`.

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
## Greenhouse Sweep - YYYY-MM-DD

Processed N companies (X had a public Greenhouse board, Y did not, Z had a fetch error).

Boards found: <list of company names that had boards>
Total postings scanned: <sum of total_jobs across swept companies>
Matched (<=5 yrs or no stated requirement + non-senior title): <count>
New to seen_jobs.json after dedup: <count>

### Sample of new matches
| Title | Company | Est. min years | Location |
|-------|---------|-----------------|----------|
| ... | ... | ... | ... |
(show up to 15; note the rest are in seen_jobs.json)

### No Greenhouse board found this batch
<company names>

Remaining: <count> companies still `greenhouse_status: pending` in company_targets.csv.
```

Then remind the user: **these are mechanically filtered, not fit-scored** — the
years-of-experience extraction is a regex heuristic and can misread ambiguous
phrasing. Suggest running `/rank` on the new batch for real fit scoring, running
`/greenhouse-sweep` again to continue through the remaining companies, and
running `/workday-sweep` on the companies this batch marked `no_board` — a
"no Greenhouse board" company may still be reachable via Workday.

---

## Important Rules

1. **One HTTP call per company for the job list** (`?content=true`) — never
   fetch each job's detail page individually in this command; that's what made
   the naive approach slow at this scale. Detail-level depth belongs to `/rank`
   and `/apply`, on a shortlist, not to a sweep of hundreds of companies.
2. **Never fabricate a Greenhouse token.** If Step 1 can't find one via
   WebSearch, the company is `no_board` for this run — don't guess a slug and
   silently treat a wrong guess's 404 as confirmation of "no board."
3. **The years-of-experience filter is a heuristic, say so.** Every summary
   this command presents must note that `estimated_min_years` is regex-based,
   not verified, and that `/rank` (or reading the posting) is the real check.
4. **Batch discipline.** Don't try to process the entire company list in one
   invocation even if asked to — that's exactly the "loop through one at a
   time" model the user asked for. Respect `--batch`, and let the user re-run.
5. **Idempotent state.** Re-running without `--recheck` never re-processes an
   already-`swept` or `no_board` company — only `pending` ones advance.
6. **This skill owns the Greenhouse columns only.** `no_board` here means "not
   found on Greenhouse" - it is not a verdict on the company overall. Never
   write to the `workday_*` columns; that's `/workday-sweep`'s state.

## Design Notes

- **Most large/established companies won't be on Greenhouse.** This is
  expected, not a bug — Greenhouse is common among startups and mid-size tech
  companies, not defense primes, big tech, or utilities (most of which run
  their own ATS). `/target-companies` already warns about this; this command
  is where that plays out in practice.
- **Why mechanical filtering instead of an LLM reading every posting:** at
  hundreds of companies and potentially thousands of postings, per-job LLM
  calls would be slow and expensive for marginal accuracy gain over a
  years-regex + title-seniority heuristic. The heuristic is deliberately
  permissive on ambiguous cases (no stated years + no seniority title → include)
  so the net stays wide; false positives get caught later by `/rank`, which
  *does* read the actual posting text with a model.
- **`estimated_min_years` boundary:** a stated "5+ years" is included (≤5), per
  the user's explicit instruction that up-to-5-years roles should be allowed
  through, even though in practice a "5+" bar at a competitive company can mean
  the realistic floor is higher. `/rank`'s Experience Match dimension is the
  place that judgment actually gets made.
