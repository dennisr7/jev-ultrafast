"""A general harness around Jev's observe and act primitives, for tool-using agents such as Claude.

Jev's own loop (agent.py) asks a hosted policy model to choose every step. This harness exposes the same
guarded browser layer directly: observe the page as a table of elements with semantic handles, act on a handle
with no model call, replay a recorded trace, or hand a goal to the Jev loop on the same tab.

The agent never supplies selectors or coordinates. A handle names an element the code observed, and every action
is checked for freshness and hit-tested before input, exactly as in the Jev loop. Mutations are never retried.
"""

import hashlib
import re

from .agent import Agent
from .browser import Browser, StalePage

OPERATIONS = {"CLICK": "click", "TYPE_TEXT": "fill", "SELECT": "select"}
CONTROLS = {
    "SCROLL_DOWN": "scroll_down",
    "SCROLL_UP": "scroll_up",
    "WAIT": "wait",
    "NEXT_EMPTY_FIELD": "next_empty_field",
}
STATE_KEYS = ("checked", "selected", "expanded", "still_empty")


class HandleError(ValueError):
    """A handle that is missing, ambiguous, or does not support the requested operation."""


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:32]


def scope_text(page, node):
    """The nearby form, dialog or row text the browser used to guard this node (empty if unknown)."""
    guard = (page.get("guards") or {}).get(str(node))
    return guard[-1] if guard and isinstance(guard[-1], str) else ""


def handles(page):
    """Map each observed node to a semantic handle: `<label>-<hash of role, label, nearby text>`.

    The handle survives re-observation, so a recorded step can find its element again after the page was
    rebuilt. Identical controls (two Delete buttons in one row group) get a `.2`, `.3` ordinal in page order.
    """
    out, seen = {}, {}
    for action in page["actions"]:
        node = action.get("node")
        if action["kind"] not in OPERATIONS.values() or node is None or node in out:
            continue
        label = action["label"].split(" → ")[0]
        raw = "|".join([action.get("role") or "", label, scope_text(page, node)[:300]])
        base = f"{slug(label) or 'element'}-{hashlib.sha1(raw.encode()).hexdigest()[:6]}"
        seen[base] = seen.get(base, 0) + 1
        out[node] = base if seen[base] == 1 else f"{base}.{seen[base]}"
    return out


def distinct(page, label, role):
    """Nodes in this observation that carry the same label and role."""
    return {
        a["node"]
        for a in page["actions"]
        if a["kind"] in OPERATIONS.values() and a.get("node") is not None
        and a["label"].split(" → ")[0] == label and a.get("role") == role
    }


def view(page):
    """The agent-facing observation: elements with handles and supported operations, plus page controls."""
    by_node = handles(page)
    elements, controls = {}, []
    names = {v: k for k, v in CONTROLS.items()}
    for action in page["actions"]:
        kind, node = action["kind"], action.get("node")
        if kind in {"scroll", "wait", "scroll_to"}:
            if action["id"] in names:
                controls.append({"operation": names[action["id"]], "label": action["label"]})
            continue
        if kind not in {"click", "fill", "select"} or node not in by_node:
            continue
        element = elements.get(node)
        if element is None:
            element = elements[node] = {
                "handle": by_node[node],
                "role": action.get("role"),
                "label": action["label"].split(" → ")[0],
                "value": action.get("value", ""),
                "operations": [],
                **{k: action[k] for k in STATE_KEYS if k in action},
            }
        operation = next(op for op, k in OPERATIONS.items() if k == kind)
        if operation not in element["operations"]:
            element["operations"].append(operation)
        if kind == "select":
            element["value"] = action.get("current_value", "")
            element.setdefault("options", []).append(action["label"].split(" → ", 1)[1])
    form = page.get("form") or {}
    return {
        "url": page["url"],
        "title": page.get("title", ""),
        "text": page.get("text", ""),
        "fingerprint": page["fingerprint"],
        "elements": list(elements.values()),
        "controls": controls,
        "required_empty": [f"{f['label']} ({f['where']})" for f in form.get("empty", [])],
        "omitted_actions": page.get("omitted_actions", 0),
    }


def render(observation):
    """The observation as a compact text table, the form a model reads cheaply."""
    lines = [f"{observation['title']} · {observation['url']}"]
    for e in observation["elements"]:
        state = ", ".join(f"{k}={e[k]}" for k in STATE_KEYS if k in e)
        value = f" · {e['value']}" if e["value"] else ""
        options = f" · options: {'; '.join(e['options'])}" if e.get("options") else ""
        lines.append(f"[{e['handle']}] {e['role']} {e['label']}{value}{options} ({'/'.join(e['operations'])}"
                     f"{'; ' + state if state else ''})")
    lines.append("controls: " + ", ".join(c["operation"] for c in observation["controls"]))
    if observation["required_empty"]:
        lines.append("required, still empty: " + "; ".join(observation["required_empty"]))
    return "\n".join(lines)


class Harness:
    """One owned browser tab driven by handle-based tools.

    Harness(url) opens its own background tab. Tests and other hosts can pass `browser=` with the same
    observe / fresh / act / close interface.
    """

    def __init__(self, url=None, *, browser=None):
        if browser is None and url is None:
            raise ValueError("Supply a url or a browser")
        self.browser = browser or Browser(url)
        self.page = None
        self.trace = []

    def observe(self):
        self.page = self.browser.observe(screenshot=False)
        return view(self.page)

    def label(self, handle):
        """The visible label for a handle in the latest observation, for approval prompts."""
        if self.page is None:
            self.observe()
        node = next((n for n, h in handles(self.page).items() if h == handle), None)
        action = next((a for a in self.page["actions"] if a.get("node") == node), None)
        if action is None:
            raise HandleError(f"No element {handle!r} on the current page")
        return action["label"].split(" → ")[0]

    def act(self, handle, operation, text=None, option=None, *, strict=True, fallback=None):
        """Execute one operation on a handle with no model call.

        strict=True refuses to act if the page changed since the last observe(), so a decision made from one
        view cannot land on another. strict=False re-observes first and finds the handle again: that is how a
        recorded trace replays. `fallback` is a recorded step; when its exact handle is gone (text near the
        element changed) and its label was unique on the page when recorded, the one element that still has
        that label and role is used. Duplicate labels never fall back, so a Delete cannot land on another row.
        Returns the executed step and the new observation.
        """
        operation = operation.upper()
        if self.page is None:
            if strict:
                raise StalePage("Observe before acting")
            self.observe()
        if not self.browser.fresh(self.page):
            if strict:
                self.page = None
                raise StalePage("Page changed since the last observation. Observe again.")
            self.observe()
        action = self._resolve(handle, operation, option, fallback)
        if operation == "TYPE_TEXT" and text is None:
            raise ValueError("TYPE_TEXT needs text")
        self.browser.act(action, self.page, text=text if operation == "TYPE_TEXT" else None)
        step = {"handle": handle, "operation": operation, "text": text, "option": option}
        if operation in OPERATIONS:
            label, role = action["label"].split(" → ")[0], action.get("role")
            step.update(label=label, role=role, unique=len(distinct(self.page, label, role)) == 1)
        # Record execution before observing: a navigation during the next observation must not erase it.
        self.trace.append(step)
        self.page = None
        try:
            observation = self.observe()
        except StalePage:
            observation = None
        return {"executed": step, "observation": observation}

    def _resolve(self, handle, operation, option, fallback=None):
        page = self.page
        if operation in CONTROLS:
            action = next((a for a in page["actions"] if a["id"] == CONTROLS[operation]), None)
            if action is None:
                raise HandleError(f"{operation} is not available on this page")
            return action
        if operation not in OPERATIONS:
            raise HandleError(f"Unknown operation {operation!r}")
        by_node = handles(page)
        node = next((n for n, h in by_node.items() if h == handle), None)
        if node is None and fallback and fallback.get("unique") and fallback.get("label"):
            matches = [n for n in distinct(page, fallback["label"], fallback.get("role")) if n in by_node]
            if len(matches) == 1:
                node = matches[0]
        if node is None:
            raise HandleError(f"No element {handle!r} on the current page")
        candidates = [a for a in page["actions"] if a.get("node") == node and a["kind"] == OPERATIONS[operation]]
        if operation == "SELECT":
            wanted = (option or "").strip().lower()
            candidates = [
                a for a in candidates if wanted in {a["label"].split(" → ", 1)[-1].lower(), a["value"].lower()}
            ]
        if not candidates:
            supported = [op for op, k in OPERATIONS.items()
                         if any(a.get("node") == node and a["kind"] == k for a in page["actions"])]
            raise HandleError(f"{handle!r} does not support {operation}{f' {option!r}' if option else ''}; "
                              f"supports {supported}")
        return candidates[0]

    def replay(self, trace):
        """Re-run a recorded trace, finding each element again by handle.

        Stops at the first step that cannot run. The caller can then hand the goal to run() to repair the flow.
        """
        for index, step in enumerate(trace):
            try:
                self.act(step["handle"], step["operation"], step.get("text"), step.get("option"),
                         strict=False, fallback=step)
            except (HandleError, StalePage, ValueError) as error:
                return {"ok": False, "failed_at": index, "error": str(error)}
        return {"ok": True, "steps": len(trace)}

    def run(self, goal):
        """Hand a natural-language goal to the Jev loop on this tab. DONE is not proof of success."""
        agent = Agent(None, goal, browser=self.browser)
        for _ in agent.run():
            pass
        state = agent.snapshot()
        self.page = None
        return {
            "status": state["status"],
            "steps": len(state["history"]),
            "url": state["page"]["url"],
            "actions": [h["action"] for h in state["history"]],
            "verified": False,
        }

    def close(self):
        self.browser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
