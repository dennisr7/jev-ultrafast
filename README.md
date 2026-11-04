# Jev Apply

An AI-assisted job application workflow. Claude finds and scores roles and drafts a tailored CV and cover letter. A browser agent (Jev) then fills the application form, one guarded step at a time, and **you** review and submit.

```
find roles          score fit           tailor documents        fill the form          you submit
/scrape  ────────►  /rank / /apply ───► CV + cover letter ────► Jev (supervised) ────► after review
(ai-job-search/)    (ai-job-search/)    (LaTeX, PDF)            (this repo's agent)
```

It never submits for you. Every run ends at a filled form in a browser tab you control.

## What is in the box

| Part | Where | What it does |
| --- | --- | --- |
| Application workspace | [ai-job-search/](ai-job-search/) | Claude Code skills and commands: set up a profile, scrape job boards, rank postings, evaluate fit, draft a CV and cover letter, prepare interviews |
| Form-filling agent | [jev_ultrafast/](jev_ultrafast/) | Reads a page as a table of controls, picks one operation and one target per step, and executes it in Chrome behind freshness and occlusion guards |
| Harness | [jev_ultrafast/harness.py](jev_ultrafast/harness.py), [tools.py](jev_ultrafast/tools.py) | The same guarded browser layer as tools: observe, act on a handle, record and replay, with an approval gate |
| Pipeline scripts | [scripts/](scripts/) | Goal builders, a rules-first step reviewer, batch runners, Workday and Greenhouse helpers, and live checks |
| Supervisor skill | [.claude/skills/supervise-jev/](.claude/skills/supervise-jev/) | Lets Claude run and review Jev tasks, and verify the final page independently |

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Chrome with remote debugging (or a separate throwaway Chrome, see step 1)
- [Claude Code](https://claude.com/claude-code) for the `ai-job-search/` commands
- Two API keys in `.env`: `TYPESAFE_API_KEY` for the hosted Jev policy model, and `TEXT_MODEL_API_KEY` for the small model that writes free-text answers (an OpenRouter-compatible key in the example configuration)
- Optional: a LaTeX distribution and `pdftotext` for CV compilation and the ATS check (see [ai-job-search/README.md](ai-job-search/README.md))

## Tutorial: fill a job application

### 1. Set up and check the browser

```bash
git clone <this repo> && cd <this repo>
uv sync
cp .env.example .env          # add TYPESAFE_API_KEY and TEXT_MODEL_API_KEY
uv run browser-harness --doctor
```

Jev needs Chrome with remote debugging. Either turn it on at `chrome://inspect/#remote-debugging` (it then shares your signed-in profile), or give Jev its own throwaway Chrome so your browser is never touched:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9333 \
  --user-data-dir=/tmp/jev-profile --no-first-run about:blank &
export BU_CDP_URL=http://127.0.0.1:9333 BU_NAME=jev
```

Check the setup before pointing Jev at anything real. Neither check calls a model or visits a website:

```bash
uv run python scripts/check_guards.py                    # 21 browser freshness and safety checks
uv run python scripts/check_harness.py --rounds 3        # the harness against a local test page
```

### 2. Pick a role and prepare documents

In Claude Code, from the `ai-job-search/` folder: `/setup` builds your profile once. `/scrape` or `/greenhouse-sweep` finds postings, `/rank` shortlists them, and `/apply <posting URL>` evaluates fit and produces a tailored CV and cover letter. Save the PDFs; Jev attaches them in step 4. Your profile and documents stay local; see [ai-job-search/README.md](ai-job-search/README.md).

### 3. Write a narrow goal

A good goal states one outcome, answers the form's own questions verbatim, lists what to leave alone, and forbids submitting. For a Greenhouse posting, list that posting's real questions first:

```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<job id>?questions=true"
```

Then write the goal in this shape. Values written as `N) Label = "value"` are typed exactly as written with no model call, which also keeps long answers from being reworded:

```text
Fill this job application without submitting it. Click "Autofill my application" if the form has it.
Answer these questions, top to bottom: 1) Are you legally authorized to work in the United States? = "Yes";
2) Will you require visa sponsorship? = "No". For a dropdown, open it and click the exact option.
Leave these blank: "Why do you want to work here?". Never touch the Voluntary Self-Identification
section or any other field. Never click Submit application. Choose DONE when every question above shows its answer.
```

Rules that keep this safe:
- Never put passwords, card numbers, government IDs or API keys in a goal.
- A question you have not answered yourself stays blank. Do not let anything guess it.
- Attestations, arbitration or AI-policy checkboxes, and voluntary self-identification are yours to answer. Leave them out of the goal.
- Keep your answers in a local file that is git-ignored, not in a shared repo.

### 4. Run it with you approving each step

```bash
uv run --env-file .env python scripts/jev_task.py --url "<application URL>" --goal "<your goal>" --step --keep-open
```

`--step` pauses before every action and prints the decision (operation, element, confidence, URL). In a second terminal answer with `python3 scripts/jev_answer.py wait` to see the pending step, then `go`, `skip` or `stop`. Check each step against your goal, and refuse anything that submits, sends or deletes. A `BLOCKED` on an unexpected page is correct behavior, not a failure. Attach the resume with `--attach FIELD_ID=/path/to/resume.pdf` if the form has an upload.

### 5. Optional: let Claude supervise

The `supervise-jev` skill runs this loop for you: it starts the task, reviews each decision against the goal, refuses Submit outright, escalates anything unusual to you, and verifies the final page. In Claude Code say, for example, "supervise Jev on this application", and review its report.

### 6. Verify and submit yourself

`DONE` is not proof. Read the final page (`artifacts/jev_task/final.jpg` and the result JSON), check every required field and answer, then click Submit yourself in the kept-open tab. To repeat a flow on a similar form, use the harness below: record a trace once and `replay` it, falling back to `run_goal` if a step fails.

## Drive it as tools (the harness)

`Agent` asks the policy model to choose every step. `Harness` exposes the same guarded browser layer directly, so you (or Claude) can act on an element without a model call, record the steps, and replay them later.

```python
from jev_ultrafast.harness import Harness, render

with Harness("https://example.com/form") as h:
    view = h.observe()                 # elements with handles, supported operations, options, required fields
    print(render(view))                # the same view as a compact text table
    name = next(e for e in view["elements"] if e["label"] == "Full name")
    h.act(name["handle"], "TYPE_TEXT", text="Ada Lovelace")
    h.act(None, "SCROLL_DOWN")
    trace = list(h.trace)              # recorded before each re-observation

with Harness("https://example.com/form") as h:
    print(h.replay(trace))             # {"ok": True, ...} or {"ok": False, "failed_at": N, "error": ...}
```

- A handle names an element the code observed (`<label>-<hash of role, label and nearby text>`). It survives a page rebuild.
- `act` refuses if the page changed since your last `observe` (`StalePage`). Observe again and decide again.
- `replay` finds each element again by handle. If the nearby text changed, it falls back to the label only when that label was unique when recorded, so a duplicate "Delete" can never land on another row. It stops at the first step that cannot run.
- `h.run(goal)` hands a natural-language goal to the Jev loop on the same tab. Its result is not verified.
- `jev_ultrafast.tools` has `TOOLS` (JSON-schema definitions: `observe`, `act`, `run_goal`, `replay`) and `dispatch(harness, name, args, approve=None)`. They match the shape Claude tool use accepts. `approve(name, args, label)` is a human gate: return `False` to refuse an action. Errors come back as `{"error": ...}` so the model can observe again. This wiring has offline tests and live checks against a local page; it has not been run end to end through the Claude API.

Details and limits: [docs/general-harness.md](docs/general-harness.md).

## How the agent works

1. **Observe.** One browser call reads visible controls, their names, values and text, and keeps references to the real DOM nodes. A whole-page checklist lists required fields still empty, in view or not.
2. **Choose.** One request asks which operation to perform (click, type, select, scroll, wait, done, blocked) and which target fits each operation. Only the target for the chosen operation is used.
3. **Guard.** Before input, the code re-checks that the page and the target are unchanged, resolves current geometry, and rejects covered or disabled controls. Model output never becomes selectors, coordinates, shell commands or JavaScript.
4. **Write text only when needed.** Values spelled out in the goal are typed verbatim. Otherwise a small model writes the value as a small JSON object.
5. **Log, then observe.** Each executed action is logged before the next observation. Mutations are never retried.

No screenshots are sent to the model in the default loop. Design notes: [docs/design.md](docs/design.md). The longer-term idea of generating custom interfaces over existing apps: [docs/meta-ui-design.md](docs/meta-ui-design.md).

## Limits

- `DONE` is a choice, not proof. Always verify the final page.
- The page reader handles common HTML and ARIA controls. Shadow roots, frames, canvas, pop-up tabs, nested scrolling and arbitrary keyboard widgets are not supported.
- Decisions come from a hosted model, so behavior can change with the model version. Pin `TYPESAFE_MODEL` for a batch.
- The Workday and Greenhouse scripts ship with placeholder answers (`[your answer]`). They do nothing useful until you supply your own, and they must stay out of any public repo once you do.
- Some employers' sites forbid automated form filling. Check before using this on one.

## Repository layout

| Path | Contents |
| --- | --- |
| `jev_ultrafast/` | The agent loop, page reader (`snapshot.js`), browser layer, model calls, harness and tools |
| `scripts/` | Task runner, step answering, reviewer, batch scripts, ATS helpers, live checks |
| `ai-job-search/` | The Claude Code workspace: skills, commands, portal CLIs, templates, tests |
| `.claude/skills/supervise-jev/` | Supervision skill and operator briefs |
| `docs/` | Design notes, harness and Meta-UI documents |
| `tests/` | Offline tests (no network, no paid APIs) |

## Development

```bash
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
```

Offline tests never call a paid API. `scripts/check_guards.py` and `scripts/check_harness.py` drive a real Chrome against local pages and make no model calls.

## License

MIT. See [LICENSE](LICENSE) and [ai-job-search/LICENSE](ai-job-search/LICENSE), which carry the copyright notices of the code this project includes.
