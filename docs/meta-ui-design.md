# Meta-UI design

Status: design only. Nothing here is built yet.

A Meta-UI is a UI wrapper generated for an existing application. Claude designs the wrapper, Jev discovers and drives the real app underneath, and the result is meant to reduce attentional residue and raise productivity. The first renderer targets a spatial XR interface in Unreal Engine on Quest 3.

## Goals

- Expose every function of the target app in the wrapper, and measure how much is covered.
- Organize the UI by task and hierarchy, so users see only what the current step needs.
- Run on any app eventually. Start with web apps that use standard controls.
- Work with hand tracking in XR as well as on a 2D screen.

## What exists today

Jev (`jev_ultrafast/`) is an observe, choose, act loop over a real Chrome tab. It produces a numbered element table, picks an operation and a target, and a small text model fills text fields. It has freshness guards, never retries a mutation, and enforces step budgets. Known limits: no iframes, shadow DOM, canvas, uploads or new tabs, a dependency on the hosted TypeSafe model, and per-company patches for application forms.

## System

### 1. Discover (build time)

Jev and Claude crawl the target app and produce a capability schema: every control found, its role, options and required inputs, and which controls are destructive.

- The crawl may execute destructive controls (delete, send, pay and similar), not just tag them. Each is recorded with a `destructive` flag.
- A crawl on a live account performs real actions. Run it on a test account or a disposable copy of the data.
- Output includes a coverage map: functions found, functions exposed in the wrapper, and functions neither. The pass-through (below) covers the gap.

### 2. Design (build time)

Claude turns the schema into a renderer-agnostic JSON spec organized as a hierarchy: app, areas, tasks, functions.

- Each action carries a function-calling schema and a safety class (safe, confirm, irreversible). Destructive actions are first-class and executable. The class sets the default confirmation behavior, not what is allowed.
- The tree is designed once and cached by schema version.
- Design rubric (hypotheses to test, not guarantees): organize by task, not by menu. Make closure explicit, with a done state and a "park this" action that records where you left off and the next step. Keep unrelated tasks out of the focused view. Preserve state across switches.

### 3. Hierarchical view

- A view renders only the current node and its direct children. Siblings and deeper levels are not built until the user navigates to them.
- Finishing or parking a task returns to its parent and records the position.
- A breadcrumb shows location. The pass-through of the original app is reachable at every level for uncovered functions.
- Each view has a small fixed budget of children and actions, which keeps every node usable with hand tracking. Schema validation enforces it.

### 4. Live generation

A fast inference service such as Groq can generate a node's view when the user navigates to it. Check current models, limits and pricing before committing, and test that the chosen model follows a strict component schema.

- Claude designs the tree and the component vocabulary offline. The fast model fills leaf views on demand, constrained to that vocabulary and the cached schema.
- Cache each generated node by schema version. Regenerate only when the app changes or the user asks. Regenerating every visit would hurt learnability and muscle memory.
- Validation gate: every generated view must pass schema validation, use only approved components, stay inside the child and action budget, and reference only actions that exist in the schema. Anything else is rejected and the cached version is used.
- Prompt injection: text from the app reaches a model that writes UI. Pass it as data fields, never as instructions, and never let generated output add actions that are not in the schema.

### 5. Execute (run time)

- Actions compile to deterministic recipes keyed by role, label and nearby context, not CSS selectors. A click runs a recipe through Jev's guarded browser layer with no model call.
- Jev is called again only to repair a recipe when the app changes.
- Destructive recipes run like any other. By default the irreversible class keeps a confirm step, configurable per action or off. Hand tracking triggers accidental activations, so where the app has an undo, a visible undo can replace the confirm.
- Jev changes needed: a direct-execution mode (stable handles, act with no model call), a change feed so the wrapper subscribes to state, and wider DOM coverage (iframes, shadow DOM) for the first target apps.

### 6. Pass-through

The original app view stays available for anything the wrapper does not cover, so the Meta-UI is never worse than the original.

## Combining apps into one task

Composition is opt-in: a user can build a task that spans several apps, or keep each app separate.

- **Tasks sit above apps.** The tree is no longer always app first. A cross-app task is a node whose functions come from more than one app's schema, and each function keeps a `source_app` tag. The app-first view stays available as another way to browse the same schema.
- **Shared entities.** Claude links functions across apps through typed values such as person, date, message or application. The output of one function (a selected email, a date) becomes the input of the next, so the user never copies data by hand.
- **One session per app.** The host keeps a separate browser session and recipe set for each app, with its own login. A combined task drives them in sequence or in parallel, and the wrapper shows one coherent state.
- **No atomic transactions.** Two apps cannot commit together. If step 2 fails after step 1 succeeded, step 1 stays done. Order steps so the riskiest or least reversible runs last, offer a compensating action where one exists (for example, un-send is not possible but "mark as follow-up" is), and show partial state clearly.
- **Data flow is visible and approved.** Data leaving one app for another is shown before it moves, and the user approves each new flow when the combined task is created. Text from app A is data in app B's actions, never instructions, which is the same injection rule as live generation. A flow that sends private data to a different service is the sharpest privacy risk here.
- **Coverage and pass-through stay per app.** Each app keeps its own coverage map and pass-through, and a combined task never hides an app's uncovered functions.
- **Maintenance.** A combined task is cached by the schema versions of every app in it. If either app changes, Jev repairs that app's recipes and the task is revalidated.
- **Verification.** Check the end result independently in each app, not only the final one.
- **Example:** an application-tracking task that reads status from a job board, matches it to emails in a mail app, and creates follow-up events in a calendar, shown as one list the user works through.

## Quest 3 and Unreal

- Jev drives Chrome over CDP, so it runs on a host machine, not the headset. The Unreal app is a thin client: it receives the JSON spec and state updates and sends intents back, over a WebSocket on the same network.
- Unreal draws each node as widgets (UMG) on world-space panels, driven by the spec.
- Hand input: Quest 3 exposes hand tracking through OpenXR and Meta's Unreal plugin. Verify the plugin version and API before committing. A small fixed gesture set (point, pinch-select, pinch-drag scroll, back, two-step confirm) maps to deterministic intents. The LLM handles only ambiguous or voice input.
- Hand input is imprecise, tiring and has no haptics. Use large targets, few actions per view, and visual and audio confirmation of every action.
- Open question: whether ambient indicators of other tasks help or hurt focus. Test a focus mode (only the active node visible) against ambient indicators, with a user switch.

## Verify

Define metrics before building and compare against the original app:

- coverage percentage
- task completion time
- error rate
- switches per task
- for destructive actions: executed correctly, and no unintended side effects, checked independently against the app's state

## Risks

- Terms of service and authentication: the wrapper drives the user's real session, and many apps restrict automation.
- Native apps need a different observer, for example the accessibility tree.
- Live generation adds vendor dependence and injection surface.
- Two vendors already sit under Jev (TypeSafe and the text model); a third adds more.

## Next steps

1. Define the spec schema and the host-to-headset message protocol, since all renderers depend on them.
2. Build a web renderer on one app and measure coverage.
3. Add the Unreal client with hand-tracking intents.
