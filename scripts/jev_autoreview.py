"""Run prepared Jev form runs under a rule-based reviewer; escalate only the unusual ones to a Haiku supervisor.

uv run python scripts/jev_autoreview.py RUN_DIR [RUN_DIR ...] [--parallel 4]

Each RUN_DIR is prepared by scripts/jev_prepare.py (goal.txt, meta.json, brief.txt). Jev runs in --step mode and
every decision is reviewed by rules derived from goal.txt. A decision is approved only if it is routine:
- scroll / wait / jump to the next empty required field,
- "Autofill my application" (Autofill forms), opening a question listed in goal.txt (or the phone Country picker),
- the goal's option for the question just opened, a goal checkbox option, the Location suggestion just typed,
- typing into a goal field (the typed text is then checked against goal.txt),
- DONE when no goal field is still empty.

Anything else ESCALATES: the run is stopped before acting, its own tab is closed (never any other tab), and the reason
is recorded. Escalation triggers: a click or field outside the goal, confidence < 0.15 on a click/typing step, 3 stale
retries in a row, a typed value that differs from the goal, BLOCKED, DONE with goal fields still empty, or a page
that leaves the form. Submit / Apply is always refused.

Finished runs are verified with jev_check_runs.py. Escalated runs: re-run scripts/jev_prepare.py for them and hand each
brief.txt to a Haiku subagent (see .claude/skills/supervise-jev/haiku-supervisor.md).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp
from jev_check_runs import check, goal_fields, norm

ROOT = Path(__file__).resolve().parents[1]
SAFE = {"SCROLL_DOWN", "SCROLL_UP", "WAIT", "NEXT_EMPTY_FIELD"}
SUBMIT = re.compile(r"\bsubmit\b|^apply( for this job| now)?$", re.I)
# Every click/typing step the rules approve already targets a goal field or goal option, so low confidence there
# usually means Jev is choosing between two correct next steps (e.g. tick a box vs fill Website). Only escalate
# when it is very low.
MIN_CONFIDENCE = 0.15
MAX_STALE = 3


def onorm(s):
    """Option text for strict comparisons: lowercase, single spaces, symbols kept (C++ is not C or C#)."""
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def same(want, got):
    """Strict option match for approvals: exact, or the option followed by more words ("United States +1")."""
    w, g = onorm(want), onorm(got)
    return bool(w) and (g == w or g.startswith(w + " "))


class RuleReviewer:
    def __init__(self, goal, autofill):
        self.fields = goal_fields(goal) + [("Country", "United States")]  # phone country picker
        self.autofill = autofill
        self.open = None  # (label, value) of the dropdown just opened
        self.typed = None  # (label, value) of the field just typed into
        self.stale = 0
        self.options = set()  # goal checkbox / multi-select options, e.g. "None of the above", "C++", "Python"
        for _, value in self.fields:
            for part in self.parts(value):
                if onorm(part) not in {"yes", "no"}:
                    self.options.add(onorm(part))

    @staticmethod
    def parts(value):
        """Options of a multi-select answer ("ML/AI, Full-Stack"); long text (essays, addresses) is one value."""
        pieces = [p.strip() for p in value.split(",")]
        return pieces if 1 < len(pieces) <= 4 and all(len(p) <= 25 for p in pieces) and len(value) < 80 \
            else [value]

    def field_for(self, element):
        e = norm(element)
        for label, value in self.fields:
            l = norm(label)[:60]
            if e and (e.startswith(l) or (len(e) >= 12 and l.startswith(e[:60]))):
                return label, value
        return None

    def review(self, decision, request):
        """("go", None) or ("stop", reason)."""
        op = decision["operation"]
        element = decision.get("element") or ""
        option = decision.get("option") or element
        if SUBMIT.search(element) or SUBMIT.search(option):
            return "stop", f"refused: would click {element!r}"
        if not decision.get("url", "").startswith("https://job-boards.greenhouse.io/"):
            return "stop", f"left the form: {decision.get('url')}"
        if op in SAFE:
            return "go", None
        if op == "BLOCKED":
            return "stop", "Jev chose BLOCKED"
        if op == "DONE":
            state = (request or {}).get("state", {})
            empty = [re.sub(r" \((above|below|in view)\)$", "", f)
                     for f in state.get("required_fields_still_empty", []) + state.get("optional_fields_still_empty", [])]
            missing = [f for f in empty if self.field_for(f)]
            return ("stop", f"DONE with goal fields empty: {'; '.join(m[:40] for m in missing)}") if missing \
                else ("go", None)
        if decision["confidence"] < MIN_CONFIDENCE:
            return "stop", f"low confidence {decision['confidence']:.2f} on {op} {element[:50]!r}"
        if op == "CLICK":
            if element == "Autofill my application" and self.autofill:
                return "go", None
            if self.open and any(same(part, option) for part in self.parts(self.open[1])):
                return "go", None
            if self.typed and norm(self.typed[0]).startswith("location") and \
                    norm(option).startswith(norm(self.typed[1].split(",")[0])):
                return "go", None
            if onorm(option) in self.options:  # a goal checkbox option, e.g. "None of the above"
                return "go", None
            field = self.field_for(element)
            if field:
                self.open = field
                return "go", None
            return "stop", f"click outside the goal: {element[:70]!r}"
        if op in ("TYPE_TEXT", "SELECT"):
            field = self.field_for(element)
            if field:
                self.typed = field
                if op == "SELECT" and not same(field[1], option):
                    return "stop", f"select {option!r} for {field[0][:40]!r}, expected {field[1]!r}"
                return "go", None
            return "stop", f"{op} outside the goal: {element[:70]!r}"
        return "stop", f"unexpected operation {op}"

    def executed(self, action):
        """After an action ran: clear the open dropdown once its option ran; check typed text."""
        self.stale = 0
        if self.open and self.parts(self.open[1]) == [self.open[1]] and same(self.open[1], action.get("action") or ""):
            self.open = None  # a single-choice dropdown is done once its option ran; multi-selects stay open
        if action.get("kind") == "fill" and self.typed:
            text, want = action.get("text") or "", self.typed[1]
            # Typing into a dropdown to filter it may use just the option text; anything else must match exactly.
            if text.strip() != want.strip() and not norm(want).startswith(norm(text)):
                return f"typed {text!r} into {self.typed[0][:40]!r}, expected {want!r}"
        return None


def own_tab(url_part, before):
    tabs = [t for t in cdp("Target.getTargets")["targetInfos"]
            if t["type"] == "page" and t["targetId"] not in before and url_part in t["url"]]
    return tabs[0] if len(tabs) == 1 else None


def run(run_dir):
    meta = json.loads((run_dir / "meta.json").read_text())
    for name in ("log.jsonl", "result.json", "control", "review.jsonl", "requests.jsonl", "stdout.txt", "final.jpg"):
        (run_dir / name).unlink(missing_ok=True)
    before = [t["targetId"] for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]
    (run_dir / "tabs_before.json").write_text(json.dumps(before))
    reviewer = RuleReviewer((run_dir / "goal.txt").read_text(), meta["autofill"])
    command = ["uv", "run", "--env-file", ".env", "python", "scripts/jev_task.py", "--step", "--keep-open",
               "--max-steps", "70", "--timeout", "120", "--output", str(run_dir), "--url", meta["url"],
               "--goal", (run_dir / "goal.txt").read_text()]
    for attachment in meta.get("attach", []):
        command += ["--attach", attachment]
    with open(run_dir / "stdout.txt", "w") as out:
        process = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                   env={**os.environ, "JEV_SAVE_REQUESTS": "1"})
    log, seen, escalation, reviews = run_dir / "log.jsonl", 0, None, []
    while process.poll() is None:
        lines = log.read_text().splitlines() if log.exists() else []
        for line in lines[seen:]:
            seen += 1
            event = json.loads(line)
            if event["event"] == "stale":
                reviewer.stale += 1
            elif event["event"] == "escape":
                reviewer.stale = max(0, reviewer.stale - 1)
            elif event["event"] == "action":
                problem = reviewer.executed(event)
                if problem and not escalation:
                    escalation = problem
            if event["event"] != "decision":
                continue
            requests = (run_dir / "requests.jsonl").read_text().splitlines() if (run_dir / "requests.jsonl").exists() \
                else []
            request = json.loads(requests[-1]).get("request") if requests else None
            verdict, reason = reviewer.review(event, request)
            if reviewer.stale >= MAX_STALE:
                verdict, reason = "stop", f"{reviewer.stale} stale retries in a row (target covered?)"
            if escalation:
                verdict, reason = "stop", escalation
            if verdict == "stop" and not escalation:
                escalation = reason
            reviews.append({"step": event.get("step"), "operation": event["operation"],
                            "element": event.get("element"), "jev_confidence": event["confidence"],
                            "verdict": verdict, "reason": reason or "rule"})
            (run_dir / "control").write_text(verdict)
        time.sleep(0.1)
    (run_dir / "review.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reviews))
    events = [json.loads(l) for l in log.read_text().splitlines() if l.startswith("{")] if log.exists() else []
    result = next((e for e in reversed(events) if e["event"] == "result"), {})
    if not escalation and result.get("outcome") != "done":
        escalation = f"run ended {result.get('outcome')}: {result.get('error') or ''}".strip()
    complete = False
    if escalation and "attach" not in escalation and "left the form" not in escalation:
        # Stopped after a refused step (e.g. typing into a field the goal doesn't mention). If the form already
        # has every goal value, it is finished: keep it rather than discard it. The check, not Jev's DONE, decides.
        pages = [t for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]
        report = check(run_dir, pages)
        complete = not report["problems"]
        # Forms without Autofill can require the voluntary self-ID questions, which goal.txt never lists; Claude
        # sets those afterwards with jev_finish.py --set (Pinterest, 2026-10-14). Keep such a form.
        if report["problems"] and all(re.search(r"required field empty: (Gender|Race|Ethnicity|Veteran|Disability|"
                                                r"Are you Hispanic)", p) for p in report["problems"]):
            complete = True
            escalation += " | needs self-ID: " + "; ".join(report["problems"])
        if not complete:
            escalation += " | check: " + "; ".join(report["problems"])[:300]
    if escalation and not complete:
        tab = own_tab(str(meta["job_id"]), set(before))
        # A long form can outrun Jev's 60-action budget (Stripe, 2026-10-14): keep it, Claude finishes the remaining
        # goal fields with jev_finish.py --set.
        if tab and "action demo budget" in escalation:
            escalation += " | tab kept: finish with jev_finish.py --set"
            tab = None
        if tab:
            cdp("Target.closeTarget", targetId=tab["targetId"])  # only this run's own, unfinished tab
    if complete:
        escalation, note = None, f"complete (rules stopped: {escalation})"
    else:
        note = None
    return {"run": run_dir, "title": meta["title"], "escalation": escalation, "note": note,
            "decisions": len(reviews), "outcome": result.get("outcome")}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()
    ensure_daemon()
    started = time.monotonic()
    with ThreadPoolExecutor(args.parallel) as pool:
        results = list(pool.map(run, [Path(r) for r in args.runs]))
    pages = [t for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]
    print(f"{len(results)} runs in {time.monotonic() - started:.0f}s\n")
    escalated = []
    for r in results:
        if r["escalation"]:
            escalated.append(r)
            print(f"[ESCALATE] {r['run'].name} {r['title'][:50]}: {r['escalation']}")
            continue
        report = check(r["run"], pages)
        status = "READY" if not report["problems"] else "CHECK"
        print(f"[{status}] {r['run'].name} {r['title'][:50]} | jev: {report['jev']}"
              + (f" | {r['note']}" if r.get("note") else ""))
        for p in report["problems"]:
            print(f"    problem: {p}")
        if report.get("not_on_form"):
            print(f"    not on this form: {'; '.join(report['not_on_form'])}")
    if escalated:
        ids = " ".join(r["run"].name for r in escalated)
        print(f"\nFor Haiku: uv run python scripts/jev_prepare.py <board> {ids}   then launch the printed prompts.")
    return 1 if escalated else 0


if __name__ == "__main__":
    sys.exit(main())
