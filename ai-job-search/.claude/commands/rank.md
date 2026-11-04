# /rank - Triage Scraped Jobs into a Ranked Shortlist

You are batch-scoring the jobs that `/scrape` has collected, so the user can decide where to spend `/apply` effort. `/scrape` finds and dedupes postings; `/apply` evaluates one at a time in depth. `/rank` is the bridge: it scores every new posting against the fit framework and returns a ranked shortlist.

`/rank` produces **triage scores**, not final evaluations. It scores from the posting text and the candidate profile only - no company research, no reviewer agent. `/apply`'s Step 1 evaluation (which adds company research) remains authoritative and always re-runs when the user applies.

Follow these steps **in order**.

---

## Step 0: Parse Input

`$ARGUMENTS` may contain:

- Nothing → rank all jobs with status `new` in `job_scraper/seen_jobs.json`
- A focus area (e.g. `/rank data science`) → rank only jobs whose title or stored fit-notes match the focus
- `--all` → re-rank every job that has not been applied to, including previously ranked ones (useful after the profile changes)
- `--top <N>` → shortlist size (default 5)

---

## Step 1: Load State

1. Read `job_scraper/seen_jobs.json`. If the file is missing or has no entries, tell the user to run `/scrape` first and stop.
2. Read `job_search_tracker.csv`. Build the exclusion set: any company+role already in the tracker is out of scope regardless of flags - it has been applied to or consciously tracked.
3. Select candidates: entries with status `new` (or all non-applied entries with `--all`), minus the exclusion set, filtered by the focus area if one was given.
4. If no candidates remain, say so ("Nothing new to rank - run /scrape to find fresh postings") and stop.
5. Read the scoring framework and profile **once**:
   - `.claude/skills/job-application-assistant/04-job-evaluation.md`
   - `.claude/skills/job-application-assistant/01-candidate-profile.md`

State how many jobs will be ranked before proceeding.

---

## Step 2: Batch-Fetch and Score

First split the candidate set in two, based on whether `seen_jobs.json` already carries a non-empty `description` field for that entry:

- **Stored-description jobs** (from `greenhouse-sweep`/`workday-sweep` - the bulk of the backlog): the posting text was already downloaded during the sweep and saved on the entry. No WebFetch needed - pass the stored `description` text straight into the agent prompt alongside the rubric. Since there's no per-job network round-trip to serialize around, batch these generously - **15-20 jobs per agent** is reasonable.
- **Unfetched jobs** (no stored `description`, e.g. from `/scrape`): unchanged from before - the agent must WebFetch the posting URL itself. Keep these at **~5 jobs per agent** since WebFetch latency and failure modes (dead links, redirects) don't parallelize as cleanly within one agent.

Dispatch parallel `general-purpose` agents (`model: "haiku"`) via the **Agent tool** for both groups. Token-efficiency rules, consistent with `/apply`:

- Pass each agent everything it needs **inline in the prompt** - the job list (title, company, URL, and stored `description` text where present) and a compact scoring rubric extracted from the files you read in Step 1: the strong/moderate/weak skill match areas, direct/adjacent experience domains, behavioral thrive/drain factors, career goals, deal-breakers, and the location constraints. Do **not** make agents re-read the profile files, and do **not** have an agent WebFetch a URL that already has stored `description` text - that defeats the point.
- For stored-description jobs, the agent scores directly from the provided text - there's no live-URL check, so these can't be marked `expired` the way a dead WebFetch link can. This is an accepted staleness tradeoff (see Design Notes): a sweep-sourced posting could have closed since it was swept, but `/rank` is triage and `/apply` always re-verifies before drafting anything.
- For unfetched jobs, agents fetch each posting URL with WebFetch and score **only from actually fetched content**. If a URL is dead, redirects to a listing page, or the posting has expired, the agent marks that job `expired` - it never scores from the title alone and never fabricates posting content.
- Scope is triage: posting text vs. rubric. **No company research, no salary lookup, no web searches** - that depth belongs to `/apply`.

Each agent returns a JSON array, one object per job:

```json
{
  "key": "<the job's key in seen_jobs.json>",
  "status": "scored" | "expired",
  "scores": { "technical": 0-100, "experience": 0-100, "behavioral": 0-100, "career": 0-100 },
  "location": "PASS" | "FAIL" | "FLAG",
  "employment_type": "PASS" | "FAIL" | "FLAG",
  "min_quals": "PASS" | "FAIL" | "UNCLEAR",
  "min_quals_quote": "<the stated minimum requirement text, or empty if none stated>",
  "deadline": "YYYY-MM-DD" | null,
  "strengths": ["1-3 bullets, grounded in the posting text"],
  "gaps": ["1-3 bullets, honest"],
  "language": "<posting language>"
}
```

**`min_quals` is a hard gate, not folded into the `experience` score** - see `04-job-evaluation.md`'s "Minimum Qualifications Gate" (4c). A stored `description` that doesn't reliably contain a "Minimum Qualifications" marker across a spot-checked sample of the batch means that batch's text is incomplete for this purpose - `min_quals` should be `UNCLEAR` for those jobs, not guessed at, and `/rank`'s Step 3 must treat `UNCLEAR` as a veto (same as `FAIL`) until a live fetch resolves it. Don't let a fast/cheap scoring model's own stated verdict go unchecked here - spot-verify a sample of `min_quals` calls against the `min_quals_quote` field before trusting the aggregate, since a model can extract the right quote and still mislabel the verdict.

Scoring uses the dimension definitions from `04-job-evaluation.md` verbatim. The honesty rule applies to triage too: gaps are stated, never smoothed over, and a posting that is a poor fit gets a low score even if it looks prestigious.

---

## Step 3: Aggregate and Rank

Back in the main context, for each scored job:

1. Compute the overall score with the weighting from `04-job-evaluation.md` (Technical 30%, Experience 25%, Behavioral 15%, Career Alignment 30%; location is unweighted).
2. Map to the framework's verdict bands (Strong Fit 75+, Good Fit 60-74, Moderate Fit 45-59, Weak Fit 30-44, Poor Fit <30).
3. **Location veto:** `FAIL` (e.g. requires relocation) excludes the job from the shortlist no matter the score - list it separately with the reason. `FLAG` (e.g. heavy travel) stays in the ranking but carries a visible ⚠ marker for the user to judge.
3b. **Minimum Qualifications veto:** `FAIL` or `UNCLEAR` on `min_quals` excludes the job from the shortlist no matter the score, listed separately with the `min_quals_quote` (or "posting text incomplete - not verified" if `UNCLEAR`). This is the same treatment as a Location FAIL - a high weighted score never overrides a stated requirement the candidate doesn't meet, or one that was never actually checked.
4. **Deadline urgency:** a deadline within 7 days gets a 🔥 marker and wins ties. A deadline that has already passed moves the job to `expired`.

Sort by overall score (descending), urgency as tiebreaker.

---

## Step 4: Update State

Update `job_scraper/seen_jobs.json` in place - these fields are additive to the scraper's schema:

- Ranked jobs: set `"status": "ranked"` and add `"rank_score": <overall>`, `"rank_verdict": "<band>"`, `"rank_date": "YYYY-MM-DD"`
- Dead or past-deadline jobs: set `"status": "expired"`

Do not modify `job_search_tracker.csv` - that file records applications, and `/rank` never applies. Re-running `/rank` is idempotent: already-`ranked` jobs are skipped unless `--all` re-scores them.

---

## Step 4.5: Update the Persistent Shortlist

`seen_jobs.json` only ever shows this run's results in Step 5's printed table - nothing keeps track of Strong/Good Fit jobs across multiple `/rank` runs over time. `shortlist.csv` at the project root is that running record. Maintain it here:

1. Read `shortlist.csv` if it exists (create with just the header row if not): `rank_date,score,verdict,title,company,location_flag,deadline,url`
2. For every job scored this run (not just newly-ranked ones re-touched by `--all`) where `rank_verdict` is `Strong Fit` or `Good Fit`, **and** it wasn't vetoed (`location_flag != FAIL` and `employment_type != FAIL`), add or update a row keyed by `url`:
   - New URL → append a row.
   - Existing URL (e.g. `--all` re-scored it) → overwrite that row in place with the new score/verdict/date rather than duplicating.
3. A job that was previously in `shortlist.csv` but re-scores below threshold or picks up a veto on a `--all` re-run gets **removed** from `shortlist.csv` - it no longer belongs on the persistent list.
4. Write the file back sorted by `score` descending.

`shortlist.csv` is a read/reference convenience, not the source of truth for applications - `job_search_tracker.csv` still owns that, and Step 1's exclusion set (jobs already in the tracker) applies before this file is touched, so an applied-to job naturally ages out of relevance here even though this step doesn't remove it automatically. Removing an applied job's row is fine to do here too, as a light cleanup, if you're already updating the file.

## Step 4.6: Refresh the Browser-Application Export

`applications/all_jobs.csv` (used for Claude-in-Chrome application sessions) sorts ranked jobs by score and shows their verdict - both of which just changed. Regenerate it:

```bash
python3 job_scraper/export_all_jobs.py
```

This overwrites the file from the current state of `seen_jobs.json` - safe to call every run, even if `--all` re-scored everything.

---

## Step 5: Present the Shortlist

```
## Job Ranking - YYYY-MM-DD

Ranked <N> new postings (<X> shortlisted, <Y> below threshold, <Z> expired/vetoed).

### Shortlist

| # | Score | Verdict | Title | Company | Location | Deadline | |
|---|-------|---------|-------|---------|----------|----------|---|
| 1 | 78 | Strong Fit | ... | ... | ... | ... | 🔥 |

### Why these ranked highest
**1. <Title> at <Company> (78)** - [2-3 strength bullets and the honest gap, from the agent's findings]
[repeat for each shortlisted job]

### Below threshold
| Score | Verdict | Title | Company | One-line reason |

### Excluded
- <Title> at <Company> - location FAIL: requires relocation
- <Title> at <Company> - expired <date>
```

Rules for the presentation:

- Every claim traces to fetched posting text or the profile - no invented details.
- Say explicitly that these are **triage scores from the posting text only**, and that `/apply` will re-evaluate with company research before anything is drafted.
- Mention that Strong/Good Fit jobs from this run were added to `shortlist.csv`, which accumulates across every `/rank` run - not just this batch.
- Then ask: "Want to apply to any of these? Give me the number(s) and I'll start with the full `/apply` workflow."
- If the user picks one, run the `/apply` workflow on that job's URL, passing the triage verdict as prior context but **re-running the full Step 1 evaluation** - triage never substitutes for it.

---

## Important Rules

1. **Never score without real posting text.** A job needs either a stored `description` (from a sweep) or a successful WebFetch. One with neither, or whose WebFetch comes back dead/redirected/expired, is marked `expired`, not guessed at.
2. **Triage depth only.** No company research, no salary lookups, no reviewer agents - `/rank` exists to be cheap enough to run on every scrape batch.
3. **Deal-breakers veto scores.** A 90-point job that fails a location deal-breaker is excluded, not ranked first.
4. **Honest scoring.** Gaps are reported per job; a low-scoring posting is presented as such. The score bands and weights come from `04-job-evaluation.md` - if the user disagrees with a ranking, the fix is updating their profile or the framework, not bending scores.
5. **State stays consistent.** `seen_jobs.json` fields are only added, never restructured, so `/scrape`'s dedup keeps working; the tracker is read-only for this command.
6. **`shortlist.csv` tracks current Strong/Good Fit status, not history.** It's keyed by `url` and kept in sync with the latest score - a job that no longer clears the bar (or later picks up a veto) is removed, not left stale.
7. **Verify posting-text completeness before trusting a batch's scores.** Before scoring any batch whose `description` came from a bulk import (a CSV, a spreadsheet, anything that isn't `greenhouse-sweep`/`workday-sweep`'s own API-sourced full text), spot-check a sample for a "Minimum Qualifications" or "Key Qualifications" marker. If it's reliably missing, treat that batch's Experience scores and `min_quals` as provisional - `min_quals` should default to `UNCLEAR` (a veto) for that batch until each shortlisted candidate is re-verified via a live fetch of the actual posting, not the imported text.

## Design Notes

- **Why stored `description` skips WebFetch:** `greenhouse-sweep` and `workday-sweep` both already download each matched job's full posting text as part of their own mechanical filtering (Greenhouse's `?content=true` list call; Workday's per-survivor detail call) and save it onto the `seen_jobs.json` entry as `description`. Since most of the backlog comes from those sweeps, re-fetching the same URL in `/rank` was pure waste - duplicate network calls, duplicate latency, and duplicate exposure to WebFetch failures on postings that were reachable moments earlier during the sweep. Jobs from `/scrape` (which doesn't bulk-download content) still need a live WebFetch, so that path is unchanged.
- **Staleness is accepted, not solved.** A stored `description` reflects the posting at sweep time, not at rank time. This is fine here specifically because `/rank` is explicitly triage-only and `/apply`'s Step 1 evaluation always re-runs with fresh company research before anything gets drafted - staleness at the triage stage never reaches the user as a final judgment.
- **Scoring agents run on Haiku, by explicit user choice.** This is a deliberate cost/accuracy tradeoff, not a default - Haiku is meaningfully cheaper/faster but scores the judgment-heavy dimensions (behavioral fit, career alignment) less carefully than the default model would. This is acceptable *because* `/rank` is triage-only and `/apply`'s Step 1 evaluation always re-runs with the default model before anything gets drafted - a sloppier triage score only risks a job being mis-ranked in the shortlist, never a bad final decision. If shortlist quality seems to degrade noticeably (jobs that clearly shouldn't score well doing so, or vice versa), that's the signal to reconsider this and go back to the default model.
- **`min_quals` verification runs on the default model, not Haiku - this is not the same tradeoff as bulk triage.** Found 2026-09-23: Haiku agents checking minimum qualifications correctly extracted the right quote (e.g. "3+ years relevant industry experience") but then mislabeled the verdict as `UNCLEAR` instead of `FAIL` for several jobs in the same batch - a carelessness failure distinct from the bulk-triage cost/accuracy tradeoff above, since here the model had the right data in hand and still got the classification wrong. Because a `min_quals` error gates real downstream effort (a wrong PASS sends a job into `/apply`'s full drafting pipeline), use the default model for this specific check even when the rest of a batch runs on Haiku, and spot-check its verdicts against its own quoted text before trusting the aggregate.
- **Bulk CSV/spreadsheet job imports are not equivalent to `greenhouse-sweep`/`workday-sweep`'s API-sourced text.** Found 2026-09-23: a user-supplied CSV of ~5,000 Apple postings contained zero "Minimum Qualifications" markers across the entire file - only a short team-summary blurb per job. A job scored 87.5/Strong Fit on that text despite requiring "BS and 5+ years of experience" per the live posting, because the stated requirement simply wasn't in the text the scoring agent saw. The mechanical years-regex filter also silently underperformed on this batch for the same reason (only 1 of 4,092 jobs got excluded on stated years, because the phrase it needs almost never appeared in the truncated text). Treat any externally-supplied job data as unverified for `min_quals` purposes until a completeness spot-check confirms otherwise.
