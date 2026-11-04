# Haiku supervisor brief

**Whole batches:** since 2026-10-12 one Haiku agent runs fill → check → fix → submit for a batch; see
[haiku-operator.md](haiku-operator.md). This file is the per-form supervision it falls back on for escalations.

Default for every Jev run (user's decision, 2026-10-11): Claude does not approve Jev's steps itself. It prepares the
run, spawns a **Haiku** subagent (Agent tool, `model: "haiku"`, `subagent_type: "general-purpose"`) with the brief
below, and checks the result. Haiku supervised a full Greenhouse form on 2026-10-11 and matched the reference reviewer
on every decision but one cautious DONE skip. It used about 83k Haiku tokens and 3 minutes per form, which is far
lighter on usage than Claude approving each step itself.

## Before spawning (Claude does this): one command

From `jev-ultrafast/`:

```bash
uv run python scripts/jev_prepare.py <board> <job id> [<job id> ...]     # runs go in artifacts/<board>/<job id>/
```

For each posting it detects whether the form has MyGreenhouse Autofill:
- **The board's own job page has Autofill.**
- **Boards that redirect to their company site don't** (e.g. Databricks). There it uses the standalone embed form
  `job-boards.greenhouse.io/embed/job_app?for=<board>&token=<id>`, adds the contact details from `CONTACT` in
  `scripts/jev_greenhouse_goal.py` to the goal, and has the runner attach the resume (`jev_task.py --attach`).

It then builds `goal.txt` from the posting's own questions, writes `meta.json` and `brief.txt` (from
[haiku-brief-template.txt](haiku-brief-template.txt)), and prints one Haiku prompt per ready posting.

**Held postings:** a posting with a required question that has no known answer (an essay, a GitHub URL, travel) is
held back and listed. Ask the user for the answer, add it to `ANSWERS` in `scripts/jev_bench.py`, and re-run
prepare. Never let Haiku or Jev guess it.

**Launch:** one Agent call per printed prompt (`model: "haiku"`, `subagent_type: "general-purpose"`). Four in parallel
worked; each run uses its own tab.

## After the runs (Claude does this): one command

```bash
uv run python scripts/jev_check_runs.py artifacts/<board>/<id> [...]
```

It is read-only. It finds each run's own tab, compares every goal field with the value on the page (including
pre-filled contact details Haiku can't see) and checks the resume. It also lists goal fields that a form doesn't
have, and summarizes Jev's confidence and Haiku's verdicts. Relay **its** result, not Haiku's checklist, and tell the
user which tabs are ready to submit.

## Rules first: `scripts/jev_autoreview.py` (default since 2026-10-11)

```bash
uv run python scripts/jev_autoreview.py artifacts/<board>/<id> [...] --parallel 4
```

**Approved by rule:** scrolling, waiting, NEXT_EMPTY_FIELD, Autofill, opening a goal question (or the phone Country
picker), the goal's option for the question just opened, a goal checkbox option, the Location suggestion just typed,
typing into a goal field (the typed text is then compared with goal.txt), and DONE when no goal field (required or
optional) is still empty.

**Escalated:** anything else, confidence below 0.3, 3 stale retries in a row, a mistyped value, BLOCKED, or leaving
the form. Escalation stops the run before acting and closes only that run's own tab. The script then prints which
IDs need Haiku and checks every finished run itself.

Results on 2026-10-11:
- **Replay of 8 past runs:** the rules approved the 7 clean ones (dropping 4 Haiku false alarms) and escalated the
  one genuinely stuck run (covered checkbox).
- **Live runs:** 5 forms in about 25 seconds each, with no Haiku tokens. Escalations it caught: a resume attach
  failure, and Jev typing into a self-ID field.

**Tuning notes:**
- Use strict option matching for approvals (`same()`: exact, or the option followed by more words). Loose substring
  matching made "No" match "Open Do you **no**w...".
- A low-confidence threshold of 0.6 escalated choices between two correct next steps (tick a box vs fill Website).
  Every rule-approved target is already goal-valid, so the threshold is 0.3, as an alarm only.

## Lessons (Databricks, 2026-10-11)

- **Pre-filled fields:** the embed form is pre-filled from the user's MyGreenhouse profile: contact details, LinkedIn,
  sometimes Voluntary Self-Identification. Haiku only sees "(filled)", so it can't verify those values;
  `jev_check_runs.py` can.
- **Required conditional questions:** Databricks' "If you selected ... other than none of the above" follow-up is
  required even after "None of the above". Answer it truthfully ("U.S. citizen"). The brief says so; Haiku stopped
  on it before the brief was fixed.
- **Location (City):** it exists only when the posting has `location_questions`. Listing it otherwise made Haiku
  refuse DONE.
- **Resume attach:** with several pages loading at once, the form's upload code may not be ready yet. The page then
  shows "Cannot read properties of undefined (reading 'uploadFile')" and that page's uploader stays broken.
  `--attach` reloads the page and attaches again (up to 3 reloads); 8/8 succeeded in testing.
- **Optional goal fields (Website = portfolio site):** Jev's checklist lists `optional_fields_still_empty`, excluding the EEO
  self-ID section. Once required fields are done, NEXT_EMPTY_FIELD can jump to an off-screen optional field.
  Without that, Jev skipped Website or tried to type into a self-ID field instead.
- **Typical run:** about 15 decisions, mean Jev confidence about 0.9, about 70k Haiku tokens, 1.5–2 min.

## Lessons (Figma, Anthropic, 2026-10-11)

- **Autofill:** some boards serve Greenhouse's own page but hide the "Autofill my application" button (Anthropic).
  `jev_prepare.py` checks the live page for the button, once per board.
- **Cut-off menus:** Jev chose "Yes" when "No" was cut off below the view. Dropdowns are now centered before
  opening, and the rules refused the wrong option every time.
- **Typing:** values the goal spells out are typed verbatim; the text helper refused a long essay.
- **Multi-selects:** a partly answered multi-select is listed as still empty ("has X; still needs Y"). Values are
  read once; the checklist had duplicated them.
- **Fields the user fills:** fields the goal leaves blank are marked "[leave blank ...]", and the jump targets the
  next goal field. Otherwise an in-view blank (an arbitration box) hid a goal field above it, and Jev declared DONE.
- **Keep complete forms:** if the rules stop a run but `jev_check_runs` passes, the form is kept.
- **Attestations and legal agreements are the user's:** AI-use policies, arbitration and similar waivers stay
  blank, via `LEAVE_BLANK` in `jev_bench.py`. Anthropic's candidate AI guidance asks applicants to write their own
  first draft of answers like "Why Anthropic?", so Claude refines it but never writes it.

