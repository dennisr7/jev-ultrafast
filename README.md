<img src="docs/banner.svg" alt="Jev Ultrafast · Browser Use × TypeSafe" width="100%" />

# Jev Ultrafast ⚡

> [!IMPORTANT]
> **The Browser Use Cloud waitlist is open.** Get early access to ultrafast browser agents in the cloud.
> **[Join the waitlist →](https://browser-use.com/ultrafast?utm_source=github&utm_medium=readme&utm_campaign=jev-ultrafast)**

**A browser agent with a dynamic, indexed action space.**

Give it one goal. [TypeSafe's Jev](https://docs.typesafe.ai/introduction) picks an operation and an element. A small LLM writes text only when the operation is `TYPE_TEXT`.

**Zürich → London on Google Flights in 7.1 seconds.** One natural-language goal, actual text generation, and loading waits included.

<a href="docs/demo.mp4"><img src="docs/demo.gif" alt="A real Google Flights search at 1× speed, with generated city names and dynamic operation/target decisions" width="100%" /></a>

[Watch the MP4](docs/demo.mp4) · [Measurements](docs/performance.md) · [Read the loop](jev_ultrafast/agent.py)

## The action space

Every observation produces a new element table:

```text
[1] button    Change ticket type · Round trip
[2] combobox  Where from?        · San Francisco
[3] combobox  Where to?          · empty
[4] textbox   Departure          · empty
...
```

The operations are `CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, and `BLOCKED`. Only supported operations and targets are offered.

```text
                      one TypeSafe request
                     ┌───────────────────────────┐
page → element table → operation                 │
                     │ click_target              │
                     │ type_text_target          │
                     │ select_target, if present │
                     └─────────────┬─────────────┘
                         use the matching target
                                   │
                    CLICK [7] ─────┤──→ browser
                TYPE_TEXT [3] ─────┘
                          ↓
                   small LLM → text → browser
```

Target questions are speculative. If the operation is `CLICK`, only `click_target` can execute. Two decisions, **one network round trip**. Each target head contains only compatible elements. Native dropdown choices carry an observed element/option index.

There are no site-specific action scripts or prepared field strings in the policy. The Flights example supplies a goal and independently verifies the outcome. The screenshot renderer adds labels afterward; it does not drive the browser.

## Try it

```bash
git clone https://github.com/browser-use/jev-ultrafast.git
cd jev-ultrafast
uv sync
cp .env.example .env
# Add TYPESAFE_API_KEY and TEXT_MODEL_API_KEY.
# Or use Jev via Vercel AI Gateway: put an AI Gateway key in TYPESAFE_API_KEY and set
# TYPESAFE_BASE_URL=https://ai-gateway.vercel.sh/typesafe
uv run jev
```

Open **http://127.0.0.1:8766** and click **Start demo → Run automatically**. The inspector shows numbered elements, operation probabilities, target probabilities, and executed actions. **Choose next** pauses before execution.

Chrome connects through [Browser Harness](https://github.com/browser-use/browser-harness), installed by `uv sync`. Run `uv run browser-harness --doctor` if it needs connecting. Allow remote debugging in Chrome when prompted.

`TEXT_MODEL_API_KEY` is an OpenRouter key in the example configuration. The current demo uses `inception/mercury-2.5` with reasoning disabled. Gemini, GLM, and DeepSeek can also use the OpenAI-compatible text helper; configure the appropriate model, endpoint, and reasoning setting.

## Use the library

```python
from jev_ultrafast import Agent

with Agent(
    "https://www.google.com/travel/flights?hl=en",
    "Find one-way flights from Zurich to London on September 20, 2026, "
    "for one adult in economy. Stop when matching flight options are visible.",
) as agent:
    for state in agent.run():
        print(state["elapsed_ms"], state["status"])
```

Run with `uv run --env-file .env python your_script.py`. The same policy can run a different task:

```bash
uv run --env-file .env python examples/run.py \
  --url https://en.wikipedia.org/wiki/Main_Page \
  --goal 'Find and open the Wikipedia article about Gödel’s incompleteness theorems.'
```

`uv run --env-file .env python scripts/jev_task.py --url URL --goal '...'` runs one task and prints a JSON result (outcome, steps, final URL, page text, `final.jpg`). Add `--step` to pause before every action and approve it with `go`, `skip` or `stop`. A `DONE` outcome still needs independent verification.

`uv run --env-file .env python examples/flights.py --keep-open` performs the flight search, checks the actual route/date/results, and saves its trace. It does not select or book a flight.

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

## Tutorial: fill a job application with ai-job-search

[ai-job-search](https://github.com/MadsLorentzen/ai-job-search) is a Claude Code workspace that finds roles, scores fit, and drafts a tailored CV and cover letter. Jev does the last step: it fills the web form, and **you** review and submit. This assumes ai-job-search is cloned and this repo sits inside it as `jev-ultrafast/`.

### 1. Set up and check the browser

```bash
cd jev-ultrafast
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

### 2. Pick a role and prepare documents (in ai-job-search)

In Claude Code, from the ai-job-search folder: `/scrape` or `/greenhouse-sweep` finds postings, `/rank` shortlists them, and `/apply <posting URL>` evaluates fit and produces a tailored CV and cover letter. Save the PDFs; Jev attaches them in step 4.

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
- Keep your answers in a local file that is git-ignored, not in this repo.

### 4. Run it with you approving each step

```bash
uv run --env-file .env python scripts/jev_task.py --url "<application URL>" --goal "<your goal>" --step --keep-open
```

`--step` pauses before every action and prints the decision (operation, element, confidence, URL). In a second terminal answer with `python3 scripts/jev_answer.py wait` to see the pending step, then `go`, `skip` or `stop`. Check each step against your goal, and refuse anything that submits, sends or deletes. A `BLOCKED` on an unexpected page is correct behavior, not a failure. Attach the resume with `--attach FIELD_ID=/path/to/resume.pdf` if the form has an upload.

### 5. Optional: let Claude supervise

The `supervise-jev` skill in ai-job-search runs this loop for you: it starts the task, reviews each decision against the goal, refuses Submit outright, escalates anything unusual to you, and verifies the final page. In Claude Code say, for example, "supervise Jev on this application", and review its report.

### 6. Verify and submit yourself

`DONE` is not proof. Read the final page (`artifacts/jev_task/final.jpg` and the result JSON), check every required field and answer, then click Submit yourself in the kept-open tab. To repeat a flow on a similar form, use the harness above: record a trace once and `replay` it, falling back to `run_goal` if a step fails.

## Why it moves

- **One request per decision cycle.** Operation and target heads share the same observed state.
- **No screenshots in the default agent loop.** Jev consumes structured state. The inspector opts into screenshots; the video uses a separate continuous screencast.
- **One browser call per snapshot.** Read visible controls, their names, values, and text atomically. Keep references to the actual DOM nodes.
- **Validate the selected target.** Clicks check the document, form values, target, and nearby context. Animation alone does not force another prediction. Resolve current geometry and reject covered controls before input.
- **Wait for useful state.** After typing into a combobox, wait for visible suggestions, capped at 200 ms. Other interactions get at most two animation frames or 50 ms. These reads happen after execution is logged.
- **Keep hidden tabs rendering.** Focus emulation prevents background animation throttling without switching Chrome's visible tab.
- **Send visible text.** Offscreen article bodies and footers do not fill the model context.
- **Reuse an interrupted text request.** A generated value survives a stale-page retry only if the entire text-helper input is unchanged.

Every executed target is resolved from an observed node. The executor rechecks page freshness and click occlusion. Model output never becomes selectors, coordinates, shell commands, or executable JavaScript. Text-helper output must parse as a small JSON object before typing.

## Small enough to read

| File | Job |
| --- | --- |
| [agent.py](jev_ultrafast/agent.py) | The complete loop and text-helper handoff |
| [snapshot.js](jev_ultrafast/snapshot.js) | Atomic DOM snapshot, indexed controls, freshness guards |
| [browser.py](jev_ultrafast/browser.py) | Browser connection, current geometry, execution |
| [model.py](jev_ultrafast/model.py) | Dynamic operation/target heads and text generation |
| [questions.py](jev_ultrafast/questions.py) | Model instructions |
| [demo.py](jev_ultrafast/demo.py) | Local inspector |

## Evidence and limits

The current video is a **7,073 ms** Google Flights run. Timing starts after initial page observation and includes model calls, generated text, browser work, stale decisions, and loading waits. A fresh independent check verifies the one-way setting, Zürich, London, September 20, 2026, and visible flight options. The video plays at 1×, with no opening hold and a 0.5-second final hold.

In six alternating runs with identical models and settings, both versions passed **3/3**. Median task time went from **9.450 s → 7.092 s**, a **25% reduction**; median browser protocol calls went from **1,092 → 101**. This is three repeats of one task on one browser profile, not a general reliability benchmark.

The same policy opened the requested Wikipedia article in **2.798 s** and passed a local hotel search/filter task in **1.896 s**. Runs, failures, source hashes, and measurement boundaries are in [performance.md](docs/performance.md).

A `DONE` choice still requires independent outcome verification. The DOM reader handles common HTML and ARIA controls, not the full accessible-name specification. Shadow roots, frames, canvas, uploads, pop-up tabs, nested scrolling, and arbitrary keyboard widgets remain outside this MVP. Owned tabs share the existing Chrome profile.

## Development

```bash
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
uv build
```

Tests are offline. `uv run python scripts/check_guards.py` checks real controls in a local browser without model calls. Live examples and recording scripts make paid API calls. `scripts/record_flights.py <new-folder>` captures original browser timestamps; `scripts/render_demo.py <recording-folder>` renders that verified run at 1× and crops out the Google account strip. Credentials and raw traces stay ignored.

---

[Browser Use](https://github.com/browser-use/browser-use) · [Browser Harness](https://github.com/browser-use/browser-harness) · [TypeSafe speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)
