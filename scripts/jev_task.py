"""One call runs Jev's loop and prints a structured result.

uv run --env-file .env python scripts/jev_task.py --url URL --goal 'A narrow goal' [--step]

Progress is one JSON object per line; the last line is the result. --step pauses before every action:
the decision is printed, then write `go` (execute), `skip` (choose again) or `stop` to the control file,
or answer the prompt on a terminal. A DONE choice is not proof of success: verify final.jpg and final_text.
Do not put credentials in a goal.
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

from jev_ultrafast import Agent
from jev_ultrafast.browser import StalePage

LOG = None  # Set by main(): every event is also appended to <output>/log.jsonl for jev_answer.py.


def emit(event, **fields):
    line = json.dumps({"event": event, **fields})
    print(line, flush=True)
    if LOG:
        with LOG.open("a") as file:
            file.write(line + "\n")


def describe(state):
    """The pending decision in the terms a reviewer needs before approving it."""
    decision = state["decision"]
    index = (decision["target"] or "").partition(":")[0]
    element = next((e for e in state["elements"] if e["index"] == index), None)
    choice = (
        next((o for o in element.get("options", []) if o["index"] == decision["target"]), None) if element else None
    )
    return {
        "step": len(state["history"]) + 1,
        "operation": decision["operation"],
        "target": decision["target"],
        "element": element["label"] if element else None,
        "option": choice and choice["label"],
        "confidence": decision["confidence"],
        "operation_probabilities": {k: round(v, 2) for k, v in decision["operation_probabilities"].items()},
        "url": state["page"]["url"],
    }


def approval(control, timeout):
    if sys.stdin.isatty():
        answer = input("go / skip / stop> ").strip().lower()
        return answer if answer in {"go", "skip", "stop"} else "stop"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.unlink(missing_ok=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if control.exists():
            answer = control.read_text().strip().lower()
            control.unlink(missing_ok=True)
            if answer in {"go", "skip", "stop"}:
                return answer
        time.sleep(0.2)
    return "stop"


def attach_file(agent, spec):
    """Set a local file on the page's <input type=file id=FIELD_ID>, then re-observe the page."""
    field, _, path = spec.partition("=")
    path = Path(path).expanduser().resolve()
    if not field or not path.is_file():
        raise ValueError(f"need FIELD_ID=PATH to an existing file, got {spec!r}")
    browser = agent.browser
    # If the form's own upload code has not loaded yet when the file arrives (common when several runs load pages
    # at once), the page shows "Cannot read properties of undefined (reading 'uploadFile')" and that page's uploader
    # stays broken: re-attaching does not help. So: attach, wait for the file name to appear, else reload the page
    # and attach again (up to 3 reloads).
    for attempt in range(4):
        if attempt:
            browser.call("Page.reload")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    if browser.evaluate("document.readyState") == "complete":
                        break
                except StalePage:
                    pass
                time.sleep(0.1)
            browser.settle()
        root = browser.call("DOM.getDocument", depth=0)["root"]["nodeId"]
        node = browser.call("DOM.querySelector", nodeId=root, selector=f'input[type="file"]#{field}')["nodeId"]
        if not node:
            raise ValueError(f"no file input with id {field!r} on this page")
        browser.call("DOM.setFileInputFiles", files=[str(path)], nodeId=node)
        deadline = time.monotonic() + 15
        shown = False
        while time.monotonic() < deadline and not shown:
            try:
                shown = browser.evaluate(f"document.body.innerText.includes({json.dumps(path.name)})")
            except StalePage:
                pass
            time.sleep(0.3)
        if shown:
            break
    else:
        raise TimeoutError(f"{path.name} did not appear on the form after 3 reloads")
    agent.state["page"] = browser.observe(screenshot=agent.screenshots)
    emit("attached", field=field, file=path.name)


def drive(agent, args, control):
    """Run to DONE/BLOCKED, the step limit, or a reviewer's stop. Returns (outcome, error)."""
    state = agent.snapshot()
    while state["status"] not in {"done", "blocked"}:
        if len(state["history"]) >= args.max_steps:
            return "step_limit", None
        try:
            if args.step:
                state = agent.command("predict")
                if os.environ.get("JEV_SAVE_REQUESTS"):
                    # What the model saw for this decision, for diagnosing low-confidence choices.
                    with open(LOG.with_name("requests.jsonl"), "a") as f:
                        f.write(json.dumps({"step": len(state["history"]) + 1,
                                            "request": state["decision"].get("request")}) + "\n")
                emit("decision", **describe(state))
                answer = approval(control, args.timeout)
                if answer == "stop":
                    return "stopped", None
                if answer == "skip":
                    continue
                before = len(state["history"])
                state = agent.command("act", {"fingerprint": state["page"]["fingerprint"]})
            else:
                before = len(state["history"])
                state = agent.command("tick")
        except StalePage as error:
            # The approved action was not executed; Jev observes again and chooses anew.
            emit("stale", reason=str(error))
            if "covered" in str(error):
                # Usually a dropdown menu still open over the target: close it, then observe again.
                agent.browser.escape()
                agent.state["page"] = agent.browser.observe(screenshot=agent.screenshots)
                emit("escape", reason="target covered; pressed Escape to close an open menu")
            state = agent.snapshot()
            continue
        except (ValueError, RuntimeError, TimeoutError) as error:
            return "error", str(error)
        if len(state["history"]) > before:
            last = state["history"][-1]
            emit(
                "action",
                **{k: last.get(k) for k in ("step", "action", "kind", "text", "probability", "page_changed", "url")},
            )
    return state["status"], None


def result_of(agent, outcome, error, output):
    state = agent.snapshot()
    try:
        page = agent.browser.observe(screenshot=True)
        (output / "final.jpg").write_bytes(base64.b64decode(page["screenshot"]))
    except Exception:
        page = state["page"]
    result = {
        "outcome": outcome,
        "error": error,
        "steps": len(state["history"]),
        "elapsed_ms": state["elapsed_ms"],
        "decision_calls": len(state["decisions"]),
        "text_calls": len(state["text_calls"]),
        "final_url": page["url"],
        "final_title": page["title"],
        "final_text": page["text"][:2000],
        "screenshot": str(output / "final.jpg") if (output / "final.jpg").exists() else None,
        "history": [
            {k: h.get(k) for k in ("step", "action", "kind", "text", "probability", "page_changed")}
            for h in state["history"]
        ],
        "note": "DONE is the model's claim, not proof. Verify the final page independently.",
    }
    (output / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", action="append", required=True, help="Repeat for an ordered list of goals.")
    parser.add_argument("--step", action="store_true", help="Pause before every action for approval.")
    parser.add_argument("--max-steps", type=int, default=60, help="Stop after this many executed actions.")
    parser.add_argument("--timeout", type=float, default=600, help="Seconds to wait for approval before stopping.")
    parser.add_argument("--output", default="artifacts/jev_task", help="Folder for log, result, final.jpg, control.")
    parser.add_argument("--keep-open", action="store_true", help="Leave Jev's tab open afterwards.")
    parser.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="FIELD_ID=PATH",
        help="Before Jev starts, put a local file into the file input with this id (e.g. resume=cv/me.pdf). "
        "Jev cannot upload files itself; this is a fixed step, not a Jev decision.",
    )
    args = parser.parse_args(argv)
    global LOG
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    LOG = output / "log.jsonl"
    LOG.write_text("")
    try:
        agent = Agent(args.url, args.goal)
    except Exception as error:
        emit("result", outcome="error", error=f"Could not start: {error}")
        return 2
    emit("started", url=args.url, step=args.step, control=str(output / "control") if args.step else None)
    for spec in args.attach:
        try:
            attach_file(agent, spec)
        except Exception as error:  # A missing field or file stops the run before Jev acts.
            emit("result", outcome="error", error=f"Could not attach {spec}: {error}")
            if not args.keep_open:
                agent.close()
            return 2
    try:
        outcome, error = drive(agent, args, output / "control")
        result = result_of(agent, outcome, error, output)
    finally:
        if not args.keep_open:
            agent.close()
    emit("result", **result)
    return 0 if result["outcome"] in {"done", "stopped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
