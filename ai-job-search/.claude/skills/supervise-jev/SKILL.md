---
name: supervise-jev
description: >
  Runs and supervises a Jev Ultrafast browser-agent task: starts scripts/jev_task.py,
  reviews each decision before it executes (--step) or lets it run to the end, then
  independently verifies the final page instead of trusting Jev's DONE. Also monitors the
  local inspector at 127.0.0.1:8766 through Claude in Chrome. Use for "run Jev on ...",
  "supervise Jev", "have Jev fill this form", "watch the Jev demo", "check if Jev's answer is right".
allowed-tools: Read, Glob, Bash(uv run *), Bash(python3 scripts/jev_answer.py *), Bash(curl -sS *)
---

# Supervise Jev

Jev picks an operation and an element from a numbered table of the page; Browser Harness executes it in the
user's real Chrome. This skill is how Claude drives that loop **as a supervisor**: one command runs a task,
each decision can be reviewed before it runs, and the outcome is verified independently.

Run every command from the Jev repo root, `jev-ultrafast/`. If the session is in the parent `ai-job-search/`
workspace, prefix each command with `cd jev-ultrafast &&` (and use `jev-ultrafast/artifacts/jev_task/` for results).
Unrelated to job applications: never use this on a job-board login, application form, or anything holding the
candidate's personal data unless the user asks and each step is reviewed with `--step`.

(Canonical copy: `jev-ultrafast/.claude/skills/supervise-jev/`. A copy in `ai-job-search/.claude/skills/` must be kept in sync.)

## Who supervises: rules first, Haiku on escalation (default)

By the user's decision (2026-10-11), Claude does not approve Jev's steps itself:
1. **Prepare:** `scripts/jev_prepare.py <board> <ids>`.
2. **Run under rules:** `scripts/jev_autoreview.py <run dirs>`. A rule reviewer derived from each goal.txt approves
   the routine decisions, refuses Submit outright, and escalates anything unusual. On escalation it stops the run
   before acting and closes only that run's own tab.
3. **Haiku for escalations only:** re-run prepare for the escalated IDs and hand each `brief.txt` to a Haiku
   subagent, as described in [haiku-supervisor.md](haiku-supervisor.md).
4. **Check:** `scripts/jev_check_runs.py` reports which tabs are ready to submit.

Claude approves steps itself only if the user asks. The review sections below are what Haiku follows.

## 0. Preflight (skip what already works)

- `.env` has `TYPESAFE_API_KEY` and `TEXT_MODEL_API_KEY` (OpenRouter, for `TYPE_TEXT`). Never print key values.
- **Direct TypeSafe key:** nothing else needed. **Vercel AI Gateway key** (`vck_...`): also set
  `TYPESAFE_BASE_URL=https://ai-gateway.vercel.sh/typesafe`. Jev is `typesafe-ai/jev` there; `TYPESAFE_MODEL=jev-latest` works.
- Test a key cheaply before a run: `POST <base>/v1/systemone` with a one-question body (`{"model":"jev-latest","state":"x",
  "questions":{"q":{"type":"noul","instructions":"Test?"}}}`). `401 authentication_error` = wrong key for that base URL
  (a Vercel key against `api.typesafe.ai` fails exactly this way). Test OpenRouter with `GET <TEXT_MODEL_BASE_URL>/auth/key`.
- A Vercel key returning `403` with *"Free tier users do not have access to this model"* means the team has no
  **purchased** credits. A budget (`vercel ai-gateway budgets ls`) is only a spend cap, and the free monthly credit does
  not unlock Jev. Check the balance without printing the key: `GET https://ai-gateway.vercel.sh/v1/credits` with the
  key as Bearer (a top-up raises `balance`). The user buys credits in the dashboard (AI Gateway → Credits); never buy them.
- Chrome must allow remote debugging. If the run cannot connect: `uv run browser-harness --doctor`. "daemon default didn't
  come up" with `DevToolsActivePort not found` in `~/.config/browser-harness/tmp/bu-default.log` means the user must turn
  it on at `chrome://inspect/#remote-debugging` (a browser security setting: they do it, not Claude) and click Allow on
  Chrome's "Allow remote debugging?" prompt.

## 1. Pick the mode

- **`--step` (default whenever in doubt).** Required for anything that submits, sends, buys, books, deletes, or
  touches a real account. Also the right mode for a task Jev has not done before.
- **Autorun (no `--step`).** For read-only, local, or throwaway tasks, or when the user explicitly wants it
  unsupervised. It has no guard against risky actions beyond the goal's own wording, `--max-steps`, and blocked detection.

**Write the goal narrowly:** one outcome, a visible stop condition, and explicit prohibitions
("Stop when matching flight options are visible. Do not select or book a flight."). Predefined form values may be
in the goal; **never put passwords, card/bank numbers, IDs, or API keys in a goal**, and do not run this on
credential or payment fields at all.

## 2. Run

Autorun (foreground, prints JSON lines, last line is the result):

```bash
uv run --env-file .env python scripts/jev_task.py --url URL --goal 'GOAL'
```

Step mode: start it **in the background** (`run_in_background: true`), because it blocks waiting for approval:

```bash
uv run --env-file .env python scripts/jev_task.py --url URL --goal 'GOAL' --step
```

Then loop: read the pending decision, judge it, answer. `jev_answer.py` writes the answer to
`artifacts/jev_task/control` and prints what happened next (the next decision, or the final result):

```bash
python3 scripts/jev_answer.py wait      # show the first pending decision
python3 scripts/jev_answer.py go        # execute it, show the next
python3 scripts/jev_answer.py skip      # do not execute; Jev chooses again
python3 scripts/jev_answer.py stop      # end the run; the tab is closed
```

Before a new run, `rm -f artifacts/jev_task/result.json`: otherwise `jev_answer.py wait` can print the **previous**
run's result and look like an instant failure. Check the run's own background output if a result looks wrong.

Flags: `--max-steps N` (default 60), `--timeout S` (approval wait, default 600, then it stops itself),
`--keep-open`, `--output DIR`. Events are also in `artifacts/jev_task/log.jsonl`; the result is `result.json`.

## 3. Reviewing each decision (step mode)

A decision line shows `operation`, `element` (and `option` for dropdowns), `confidence`,
`operation_probabilities`, and the page URL. Before `go`, check all of:

1. Does this move the **goal** forward, and is the element the right one (label, and for `TYPE_TEXT` the field)?
2. Is it one of the **prohibited** things in the goal, or an irreversible one (submit, send, pay, confirm, delete)?
   If so, stop and ask the user; do not `go`.
3. Is the URL still on the expected site? An unexpected page means something else used the browser (this happened once:
   the user changed the tab). A `BLOCKED` on the wrong page is **correct**; do not treat it as a Jev failure.
4. Low confidence (< ~0.5) is normal for early steps; act on it only when it also fails 1-3. Be suspicious of
   `DONE` when the goal's requirements are not all visible yet, and of repeated `WAIT`.
5. Typed values (`action` events with `text`) must match what the user supplied or what the goal implies.

`skip` re-chooses without acting and is cheap; use it for a doubtful step before resorting to `stop`.

A `stale` event after `go` means the approved action was **not** executed (the page changed in between) and Jev
chose again; approve the repeat if it is still right. One stale retry right after opening a dropdown is normal.
Do not conclude a run is stuck from a single repeat. `Browser.settle()` waits for a freshly loaded page to stop
changing, so the first decision is no longer stale on pages that hydrate late (Greenhouse forms).

## Job-application forms (Greenhouse)

Learned on Anduril's Greenhouse board (2026-10-10/11); applies to any `job-boards.greenhouse.io` form.

- Only with the user's request, `--step` (a person approving, or `scripts/jev_bench.py`'s allowlist reviewer), and a
  goal that ends "Never click Submit application". Add `--keep-open` when the user will submit from that tab.
- Tell Jev not to click the top "Apply" button and to click **"Autofill my application"**: MyGreenhouse fills contact
  details, resume, education and the voluntary demographics from the user's saved profile. Jev answers only the
  company's custom questions, each listed in the goal as `question = "exact option label"`.
- Get each posting's custom questions first from the public API, so the goal covers them and no answer is guessed:
  `curl -s "https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>?questions=true"`. Questions vary per posting.
  Answers the user has not given (birth country, citizenships, essays) stay blank; say so in the goal ("Leave X blank").
- **"Previously applied" / "History with <company>":** check the real history instead of leaving it blank. In the
  ai-job-search workspace, `applications/greenhouse_applied.csv` (refreshed every 15 min by
  `job_scraper/greenhouse_applied.py`) lists every MyGreenhouse application. Any earlier application there = "Yes".

### What Jev sees on a form (since 2026-10-11)

Jev observes only the viewport, so each observation also carries a **whole-page checklist** (`snapshot.js` → `form`):
- `required_fields_still_empty` (with above / in view / below) and `required_fields_answered` (dropdowns with their
  chosen value; typed fields only as "(filled)") are sent to the model. Elements of empty required fields carry
  `still_empty`; dropdown elements show their chosen answer as `value`.
- **`NEXT_EMPTY_FIELD`** (a control like SCROLL_DOWN) jumps to the next empty required field *below* the view. It is
  offered only when no empty required field is in view. Safe to approve.
- **BLOCKED with an empty required field is overridden:** Jev scrolls to that field and chooses again, at most twice
  per field. It appears as an action "Scroll to required field still empty: X".
- Expect **DONE** at the end. BLOCKED with an empty checklist means "probably finished, unsure": verify, don't retry.
- Fields left blank on purpose stay in the empty list forever, so Jev relies on the goal's "leave blank" wording there.
  Confidence stays lower on such forms (about 0.68 on Anduril's Omen form, vs about 0.85 elsewhere). That's normal.
- Dropdowns take two approvals: `Open <question>`, then the option. A second click on the same dropdown right after
  opening it, or one stale retry, is normal: the menu is still rendering.
- Pace: about 13 to 30 actions per form. Under the benchmark reviewer a form takes about 30 seconds; with a person
  approving, the approvals dominate.

### Verifying a form

`final_text` holds only the visible viewport, so read the form itself: `scripts/jev_read_form.py snapshot` before the
run, `read URL` after it (read-only; prints every required field from Jev's own new tab). Under the hood, over CDP:
`cdp("Target.getTargets")`, attach to Jev's tab with `Target.attachToTarget(..., flatten=True)`, then evaluate
`READ_STATE` (`jev_ultrafast.browser`) and read `form.empty` / `form.answered`. For each answer, a react-select
dropdown's value is the `[class*="single-value"]` inside its own `[class*="control"]`; don't climb further, or you
read a neighbouring widget. Greenhouse's phone **Country** field shows the dial code (`+1`); that is correct.

**Tab safety.** Several tabs can show the same form: the user's own copy, older runs, the one to submit. Identify Jev's
tab as the one that is **new since the run started** (record `Target.getTargets` IDs before launching). Never read or
close "the last tab on this URL": that once closed the user's ready-to-submit tab. Never close a tab the user will
submit from.

### Benchmarking (`scripts/jev_bench.py`)

`uv run python scripts/jev_bench.py <job id> [...] --label NAME` runs each form under an allowlist reviewer:
- It approves only scrolling, waiting, `NEXT_EMPTY_FIELD`, DONE/BLOCKED, Autofill, opening a known question, the
  expected option for the question just opened, and typing "How did you hear".
- Anything else, Submit included, stops the run.
- It then scores the answers on the run's own tab and closes only that tab.
- Answers live in `ANSWERS` / `LEAVE_BLANK` at the top; edit those for another company or candidate.
- Output: `artifacts/bench/NAME/` holds each form's log, `run_<id>/requests.jsonl` (exactly what the model saw at
  every decision) and `summary.json`.

To raise confidence, look at the low-confidence decisions' `operation_probabilities` and their request, not at guesses:
- The biggest win so far was a bug found this way: answered dropdowns were missing from the checklist because
  react-select makes its input transparent once a value is chosen.
- A single run varies by about ±0.05, so compare on several forms before keeping a prompt change.
- Rewording DONE/BLOCKED once lowered confidence (0.81 → 0.74) and was reverted.

Results on 5 Anduril forms: mean confidence 0.62 → 0.83, 5/5 end in DONE, 42/42 answers correct.

## 4. Verify the outcome independently

**A `DONE` choice is not proof.** After the result line:

- `Read` `artifacts/jev_task/final.jpg` and inspect `final_text` / `final_url` in `result.json`.
- Check each requirement of the goal against them (route, date, filters, selected item, typed values, "no booking made").
  Write a goal-specific check; `examples/flights.py verify()` is hardcoded to one date and only a pattern to copy.
- Report pass/fail per requirement, then the summary below. If anything fails, say so plainly; do not soften.

## 5. Watching through Claude in Chrome (optional)

- `scripts/jev_task.py` drives its own background tab, which is **not** in Claude in Chrome's tab group and may not
  be visible. Verify with `final.jpg` and `final_text`, not by looking for that tab.
- To watch the inspector demo instead: open `http://127.0.0.1:8766` in a **new** tab you create, and read
  `curl -sS http://127.0.0.1:8766/api/state` (read-only, no token). Do not click its controls unless the user asked.
- Never navigate, click in, or close Jev's tab. Do not fetch the inspector's `X-Demo-Token` or POST to `/api/*` without
  the user's go-ahead: it lets Claude drive their signed-in Chrome.

## 6. Report back

`outcome` (done / blocked / stopped / step_limit / error), steps and elapsed time, decisions reviewed and any skipped or
stopped (with why), the independent verification checklist, and anything unresolved. One paragraph plus the checklist.

## Known limits

Frames, shadow DOM, canvas, file uploads, pop-up tabs, nested scrolling, and arbitrary keyboard widgets are outside Jev's
reader. The gateway and the direct TypeSafe API return the same shapes; nothing here changes Jev's own guards.
Do not commit or push unless the user asks.
