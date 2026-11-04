"""Check finished Jev form runs in one pass. Read-only: never clicks, types, navigates, or closes a tab.

uv run python scripts/jev_check_runs.py RUN_DIR [RUN_DIR ...]     # e.g. artifacts/databricks/*/

For each run folder (made by scripts/jev_prepare.py: goal.txt, meta.json, tabs_before.json, log.jsonl):
- finds the run's own tab: new since tabs_before.json and showing this job (never any other tab),
- reads every field on the form and compares it with each `label = "value"` in goal.txt,
- checks the attached resume, and summarizes Jev's outcome/confidence and the supervisor's verdicts.

A goal field the form does not have is listed as "not on form" (fine). Exit code 1 if any run has a problem.
"""

import json
import re
import statistics
import sys
from pathlib import Path

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp

# Every labelled field on the page with its current value: dropdowns as chosen option(s), checkbox and radio
# groups as the ticked labels, text fields as typed.
READ = r"""(() => {
  const text = e => (e?.innerText || e?.textContent || '').replace(/\s+/g, ' ').trim();
  const labelOf = e => text(document.getElementById(e.getAttribute('aria-labelledby') || '')) ||
    e.getAttribute('aria-label') || text(e.labels?.[0]) || '';
  const out = [];
  for (const e of document.querySelectorAll('input:not([type=hidden]):not([type=file]),textarea,select')) {
    if (['checkbox', 'radio'].includes(e.type)) continue;
    const label = labelOf(e);
    if (!label) continue;
    let value = e.value ?? '';
    if (e.getAttribute('role') === 'combobox') {
      const control = e.closest('[class*="control"]') || e.parentElement?.parentElement;
      const picked = [...(control?.querySelectorAll('[class*="single-value"],[class*="multi-value__label"]') || [])]
        .map(text).filter(Boolean);
      value = picked.join(', ');
    } else if (e.tagName === 'SELECT') {
      value = [...e.selectedOptions].map(o => o.label).join(', ');
    }
    out.push([label, value]);
  }
  for (const group of document.querySelectorAll('fieldset,[role=group],[role=radiogroup]')) {
    const boxes = [...group.querySelectorAll('input[type=checkbox],input[type=radio]')];
    if (!boxes.length) continue;
    const label = text(group.querySelector('legend')) || labelOf(group);
    out.push([label, boxes.filter(b => b.checked).map(b => text(b.labels?.[0]) || b.value).join(', ')]);
  }
  return {fields: out, body: document.body.innerText};
})()"""


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def goal_fields(goal):
    # Numbered answers follow ": " or "; " ("... top to bottom: 1) Label = "value"; 2) ..."), never "(+1) as".
    return [(m[0].strip(), m[1]) for m in re.findall(r'(?:: |; )\d+\) (.+?) = "([^"]*)"', goal, re.S)]


def matches(want, got, label=""):
    """Exact, or one of several ticked options, or an autocomplete showing a shorter form ("Springfield, FL")."""
    got_parts = [p.strip() for p in got.split(",")]
    if re.search(r"location|city", label, re.I):
        return norm(want.split(",")[0]) == norm(got_parts[0])
    want_parts = [p.strip() for p in want.split(",")]
    if 1 < len(want_parts) <= 4 and len(want) < 80 and not re.search(r"\d", want):
        # A multi-select answer: exactly the same options, in any order (symbols kept: C++ is not C).
        key = lambda p: re.sub(r"\s+", " ", p.lower()).strip()
        return {key(p) for p in want_parts} == {key(p) for p in got_parts}
    return (norm(want) == norm(got) or norm(want) in map(norm, got_parts) or norm(want) in norm(got)
            or (norm(want.split(",")[0]) and norm(want.split(",")[0]) == norm(got_parts[0])))


def check(run, pages):
    meta = json.loads((run / "meta.json").read_text()) if (run / "meta.json").exists() else {}
    job = meta.get("job_id") or run.name
    report = {"run": run.name, "title": meta.get("title", "")}
    events = [json.loads(l) for l in (run / "log.jsonl").read_text().splitlines() if l.startswith("{")] \
        if (run / "log.jsonl").exists() else []
    result = next((e for e in reversed(events) if e["event"] == "result"), {})
    confidences = [e["confidence"] for e in events if e["event"] == "decision"]
    report["jev"] = f"{result.get('outcome', 'no result')}, {len(confidences)} decisions" + (
        f", mean conf {statistics.mean(confidences):.2f}, min {min(confidences):.2f}" if confidences else "")
    if result.get("error"):
        report["jev"] += f" ({result['error'][:90]})"
    if (run / "review.jsonl").exists():
        verdicts = [json.loads(l).get("verdict") for l in (run / "review.jsonl").read_text().splitlines()
                    if l.strip().startswith("{")]
        report["supervisor"] = {v: verdicts.count(v) for v in sorted(set(verdicts))}
    if not (run / "tabs_before.json").exists():
        report["problems"] = ["no tabs_before.json: cannot tell which tab is this run's"]
        return report
    before = set(json.loads((run / "tabs_before.json").read_text()))
    tabs = [t for t in pages if t["targetId"] not in before and str(job) in t["url"]]
    if len(tabs) != 1:
        report["problems"] = [f"expected this run's 1 tab, found {len(tabs)}"]
        return report
    session = cdp("Target.attachToTarget", targetId=tabs[0]["targetId"], flatten=True)["sessionId"]
    page = cdp("Runtime.evaluate", session_id=session, expression=READ, returnByValue=True)["result"]["value"]
    fields = [(norm(label), value) for label, value in page["fields"]]
    problems, absent = [], []
    for label, want in goal_fields((run / "goal.txt").read_text()):
        key = norm(label)[:60]
        found = [value for l, value in fields if l.startswith(key) or (len(l) >= 12 and key.startswith(l))]
        if not found:
            absent.append(label[:50])
        elif not any(matches(want, value, label) for value in found):
            problems.append(f"{label[:50]}: has {found[0]!r}, expected {want!r}")
    for attachment in meta.get("attach", []):
        name = Path(attachment.partition("=")[2]).name
        if name not in page["body"]:
            problems.append(f"attachment {name} not on the form")
    # Not in goal.txt but needed to submit: Autofill can silently not run (Figma, 2026-10-12), leaving these empty.
    for label in ("first name", "last name", "email", "phone"):
        if any(l.rstrip("*").strip().lower() == label and not value for l, value in page["fields"]):
            problems.append(f"{label} is empty (Autofill did not run? try jev_finish.py --autofill)")
    if not re.search(r"Resume/CV[\s\S]{0,60}\.(pdf|docx?)", page["body"], re.I):
        problems.append("no resume attached")
    for label, value in page["fields"]:
        if label.endswith("*") and not value and not re.search(r"^(country|search|location \(city\))", label, re.I):
            problems.append(f"required field empty: {label[:50]}")
    report["problems"] = problems
    if absent:
        report["not_on_form"] = absent
    return report


def main(runs):
    ensure_daemon()
    pages = [t for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"]
    bad = False
    for run in runs:
        report = check(Path(run), pages)
        status = "OK" if not report["problems"] else "CHECK"
        bad |= status != "OK"
        print(f"[{status}] {report['run']} {report['title'][:55]}")
        print(f"    jev: {report['jev']}" + (f" | supervisor: {report['supervisor']}" if "supervisor" in report else ""))
        for p in report["problems"]:
            print(f"    problem: {p}")
        if report.get("not_on_form"):
            print(f"    not on this form: {'; '.join(report['not_on_form'])}")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
