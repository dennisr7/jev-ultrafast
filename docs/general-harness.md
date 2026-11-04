# General Jev harness

A harness that lets a tool-using model such as Claude do computer use through Jev's guarded browser layer, instead of through screenshots and free-form actions. This document explains how Jev works today, how a general harness builds on it, what is implemented, and what is not.

Status: the first slice is implemented (`jev_ultrafast/harness.py`, `jev_ultrafast/tools.py`, tests in `tests/test_harness.py`). Everything under "Roadmap" is design only. Evidence for Jev's speed comes from `docs/performance.md`: three matched pairs on one live task, too few for a strong statistical claim.

## 1. The core idea

A general computer-use model usually sees a screenshot, reasons about it, and emits free-form actions such as "click at (x, y)". Each step pays for an image, a long generation, and a chance to mis-ground coordinates.

Jev turns the step into a **finite choice over structured state**:

- The page becomes a numbered table of real controls.
- A model picks one operation and one target from that table in a single request.
- A small text model writes words only when typing is needed.
- Code, not the model, executes the action, behind guards.

The model never emits a selector, coordinate or script. It can only choose among things the code observed.

## 2. How the Jev loop works

### 2.1 Attach
`Browser` (`browser.py`) uses Browser Harness over the Chrome DevTools Protocol. It creates its own background tab with a fixed 1120x780 viewport and focus emulation, so animations and menus keep rendering without taking over the user's tab. `settle()` waits until a page marker stops changing for 0.5 s (cap 5 s), so late hydration does not make the first decision stale.

### 2.2 Observe in one read
`snapshot.js` runs in a single `Runtime.evaluate` and returns:

- **Identity:** a code-owned numeric ID per element (`WeakMap` plus a live `Map`). Replaced elements get new IDs, navigation resets the cache. These are not CDP node IDs.
- **Controls:** links, buttons, inputs, textareas, selects, summaries, contenteditable elements and ARIA roles. Password, file and hidden inputs are excluded. Up to 250 candidates are kept.
- **Names:** `aria-labelledby`, `aria-label`, labels, button values, alt text, child text, title, placeholder.
- **State:** value, checked, selected, expanded, disabled, read-only.
- **Visible text, URL, scroll position.**
- **Whole-page form checklist:** required fields still empty anywhere on the page (above, in view, below), required fields already answered, and capped optional empty fields. Custom dropdowns are read through their placeholder and value elements. Voluntary self-identification (EEO) fields are never surfaced.
- **Freshness data:** a page marker, a page key, and a per-element guard (role, name, value, state, href, and up to 6,000 characters of nearby form, dialog or row text).

No screenshot is sent to the model. Screenshots are optional, for the inspector and recordings.

### 2.3 Build the action space
`action_space()` (`model.py`) gives each node one index even if it supports both clicking and typing, and groups targets by operation: CLICK, TYPE_TEXT, SELECT (dropdown options are `index:option` targets). Scroll up/down, WAIT and `next_empty_field` are offered as operations, plus DONE and BLOCKED. Only operations with targets on this page are offered.

### 2.4 One request, several answers
`choose()` sends one POST to TypeSafe `/v1/systemone` with the goal, shared rules (`questions.py`), page URL/title/text, the element table, the form lists and the last 10 actions. It asks an **operation question** and a **target question per operation** in the same round trip. Only the target head matching the chosen operation is used.

### 2.5 Validate
`validate_choice()` rejects a response unless the choice is offered, the probabilities cover exactly the offered IDs, every number is finite and within [0, 1], they sum to about 1, and the chosen option has the highest probability.

### 2.6 Generate text only when needed
If the goal spells out a value (`N) label = "value"`), `goal_value` types it verbatim with no model call. Otherwise `field_text` asks a small OpenAI-compatible model for JSON with one `text` value.

### 2.7 Guard, then execute
`Agent.command("act")` and `Browser.act` apply, in order:

1. The decision is consumed once, before any mutation, so a retry cannot double-click.
2. The fingerprint must match the page the decision was made on.
3. `Browser.fresh()` compares the target's guard (and for forms the page key) with the live page. Unrelated animations do not invalidate it. A changed label, value, nearby context or disabled state does.
4. In the page, the executor checks the node is connected, enabled, visible, writable if typing, and not covered (`elementFromPoint`).
5. Input is real CDP input: mouse press and release at the element center; typing is select-all then `Input.insertText`; native dropdowns set the value and fire `input` and `change`.
6. The action is logged **before** the next observation.

A failed check raises `StalePage`, the code re-observes, and the model chooses again. Mutations are never retried. An interrupted native-select stops the run because its change event may already have fired.

### 2.8 Wait smartly and stop safely
After an interaction the next observation waits up to two animation frames or 50 ms, and for editable comboboxes until suggestions are visible (cap 200 ms). Open menus are scrolled into view. A run ends on DONE, BLOCKED, the action or decision budget (60 and 120), or three consecutive actions that leave the page unchanged. BLOCKED while a required field is empty is redirected to that field, at most twice per field.

### 2.9 Measured effect
From `docs/performance.md` (Google Flights, optimized runtime): 7.09 s median verified task time, 17 model requests, median decision latency 178 ms, about 101 browser protocol calls (down from 1,092). Efficiency comes from structure: no image tokens, one request for operation and target, one-read snapshot, semantic freshness instead of re-planning on every DOM mutation, short outputs.

## 3. How Claude uses it

Jev is a fast executor policy, not a planner. Claude's role is:

- **Goal writer:** one outcome, a visible stop condition, explicit prohibitions, predefined values. Never credentials.
- **Supervisor:** in `supervise-jev`, each decision can pause for approval (`--step`). At scale a rule reviewer approves routine steps, refuses Submit outright and escalates the unusual to a Haiku subagent.
- **Verifier:** the final page is checked independently. DONE is never treated as proof.

The gain for a Claude-based system is where tokens go: planning, judgment and verification on the large model, and the perceive-and-click loop on a cheap specialized one.

## 4. The general harness (implemented)

The Jev loop makes a model call for every step. The harness exposes the guarded browser layer directly, so a tool-using agent (or a recorded flow) can act without that call.

### 4.1 Semantic handles
`harness.handles(page)` names each element `<label>-<hash>` where the hash covers role, label and up to 300 characters of nearby scope text. The handle survives re-observation and node-ID changes. Identical controls in identical context get `.2`, `.3` ordinals in page order, which can drift if the page reorders them (a known weakness).

### 4.2 `Harness` API (`harness.py`)

| Call | What it does |
|---|---|
| `Harness(url)` or `Harness(browser=...)` | Own a background tab, or wrap any object with the same observe/fresh/act/close interface (tests use a fake) |
| `observe()` | Elements with handles, supported operations, options, state, page controls, required-empty fields, omitted-action count |
| `render(observation)` | The same as a compact text table a model reads cheaply |
| `act(handle, operation, text=None, option=None, strict=True)` | One guarded operation with no model call. `strict=True` refuses if the page changed since the last observe. `strict=False` re-observes first and finds the handle again |
| `replay(trace)` | Re-runs recorded steps by handle. Stops at the first step that cannot run and reports where |
| `run(goal)` | Hands a goal to the Jev loop on the same tab. Result has `verified: False` |

Operations: CLICK, TYPE_TEXT, SELECT, SCROLL_DOWN, SCROLL_UP, WAIT, NEXT_EMPTY_FIELD. Executed steps are recorded in `trace` before the next observation, so a navigation cannot erase them.

### 4.3 Tool definitions (`tools.py`)
`TOOLS` lists `observe`, `act`, `run_goal` and `replay` as JSON-schema tools that Claude tool use or an MCP server can accept as-is. `dispatch(harness, name, args, approve=None)` runs one call and returns a JSON-serializable result. A stale page or bad handle returns `{"error": ...}` so the agent can observe again. `approve(name, args, label)` is a human gate: returning False refuses the action. Irreversible actions should always pass through it.

### 4.4 Other changes
- `Agent` accepts `browser=` and then does not close a browser it does not own, so `run()` shares the harness's tab.
- `model.post_json` now retries transport failures (not only HTTP 429/503/529) three times with backoff. Model requests change nothing in the browser, so this is safe.

### 4.5 Intended usage patterns
1. **Interactive tool use.** Claude calls `observe`, decides, calls `act`, reads the returned observation. Each step costs Claude one small text turn and no model call to Jev.
2. **Record and replay.** A flow Claude (or Jev) completed once is stored as a trace. Later runs call `replay`, which costs no model calls. On failure, fall back to `run_goal` to repair, then re-record.
3. **Supervised.** Pass `approve` to `dispatch` so a person or a rule reviewer sees the label of every action first.

## 5. Not implemented yet (roadmap)

- **MCP server wrapper.** `TOOLS` and `dispatch` are protocol-neutral. A wrapper still has to be written and given a lifecycle for sessions.
- **Hybrid routing.** When observation shows something unsupported (canvas, frames, uploads), escalate that step to a vision-based Claude computer-use call, then return to the fast path.
- **Recipe store.** Persist traces per site and flow, version them, and track success rates. Today a trace is only an in-memory list.
- **Structured goals.** Replace the regex-parsed goal text with a JSON object rendered to text for the model, plus a post-run report of goal values that were never typed.
- **Per-run state.** Run IDs and directories for control, log and result files, with atomic writes.
- **Wider observer.** Shadow DOM, iframes, uploads, new tabs, nested scrolling, keyboard widgets.
- **Dedicated browser profile** instead of the user's Chrome.
- **Other surfaces** through an accessibility-tree observer, for the Meta-UI plan (`docs/meta-ui-design.md`).
- **Live-site evidence.** The new code has offline tests only (a fake browser). It has not been run against a real page. A first live check should use a local fixture page, as `scripts/check_guards.py` does.

## 6. Limits to keep in mind

- The decision model is a closed hosted service, and the repo's evidence covers two sites plus internal form-filling runs.
- Handles are derived from visible text. A page that changes labels or context breaks a recorded trace, which is why `replay` reports the failing step.
- A valid action can still be wrong. Verify outcomes independently.
- Scoped freshness guards deliberately allow unrelated page changes. This is a heuristic.
- The harness inherits Jev's untrusted-text rule: page text is data, never instructions. A tool-using agent must keep treating it that way.
