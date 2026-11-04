# Haiku operator: one Haiku agent runs a whole batch

User's decision (2026-10-12): to save credits, a **Haiku** subagent runs the mechanical part of a batch end to end.
Claude keeps only the judgment work: surveying boards, evaluating fit, and getting answers or essays from the user
into `ANSWERS` in `scripts/jev_bench.py`. Claude also gets the user's yes to submit.

## Claude: before spawning

1. Pick the postings (fit evaluated, shown to the user).
2. Make sure every required question has an answer: `uv run python scripts/jev_prepare.py <board> <ids...>` must
   say `Held for answers: 0`. A held posting is never given to Haiku.
3. Spawn one agent: Agent tool, `model: "haiku"`, `subagent_type: "general-purpose"`, with the prompt below. Fill
   in the runs, and `SUBMIT: yes` only if the user said to submit this batch in chat. Otherwise use `SUBMIT: no`.

## Prompt (copy, fill the two lines)

```
You operate the Jev form pipeline in ~/ai-job-search/jev-ultrafast (run every command from there).
RUNS: <board>/<id> <board>/<id> ...          (each is artifacts/<board>/<id>)
SUBMIT: yes|no

Steps, in order. Use only these scripts; never edit files, never answer a question that is not already in goal.txt.
1. Fill: uv run --env-file .env python scripts/jev_autoreview.py artifacts/<board>/<id> ... --parallel 4
   For any [ESCALATE] run: re-run jev_prepare.py for that id only, then follow its brief.txt yourself (it is the
   step-by-step supervisor brief), at most once per run.
2. Check: uv run python scripts/jev_check_runs.py <run dirs>
   Fix only these problems, then check again (at most twice):
   - "first name is empty" / contact fields empty  -> uv run python scripts/jev_finish.py <run> --autofill
   - a goal dropdown that is empty or wrong        -> uv run python scripts/jev_finish.py <run> --set 'LABEL REGEX=Exact option'
   - required demographic question empty (no Autofill forms): these are the applicant's own answers. Use only
     what the goal or profile states; if it states nothing, report it and do NOT guess.
   Anything else (agreement, arbitration, essay, GPA, password, CAPTCHA, unknown question): do NOT fix. Report it.
3. Submit, only if SUBMIT is yes and the run is [OK]: one run at a time,
   uv run python scripts/jev_finish.py <run> --submit, then wait 30-60 s before the next.
   "email verification code requested" or "CAPTCHA shown": stop submitting that run, report it. Never enter a code.
4. Reply with one line per run: id, title, final status (submitted / ready / held: reason), and every
   problem you could not fix. No other commentary.
```

## Claude: after

Re-run `jev_check_runs.py` or `jev_finish.py --state` on anything Haiku reports as not submitted. Then tell the user
what was submitted, what needs them (codes, agreements, held questions), and add submitted roles to the tracker
(MyGreenhouse picks most up within 15 minutes).
