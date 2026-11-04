"""Record answers for questions wd_apply.py handed off in artifacts/workday/<tenant>/pending.json (2026-10-24).

uv run python scripts/wd_answer.py show <tenant>                       print the pending questions and their options
uv run python scripts/wd_answer.py set <tenant> "<label>" "<option>" --why "<profile fact or 'the applicant said ...'>"
uv run python scripts/wd_answer.py yours <tenant> "<label>"            leave this question for the applicant on every run

Answers go to wd_answers.json by_question[<tenant>][<exact label>], so the next run (and every later application at
that company) answers them without judgment. An option must be one the form offered, and every answer needs a why:
an answer that cannot point to a profile fact or something the applicant said belongs to him ("yours"), not to a guess.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANSWERS = ROOT / "scripts" / "wd_answers.json"


def pending(tenant):
    p = ROOT / "artifacts" / "workday" / tenant / "pending.json"
    return json.loads(p.read_text()) if p.exists() else {"questions": []}


def norm(label):
    return re.sub(r"\s+", " ", label).strip().rstrip("*").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["show", "set", "yours"])
    ap.add_argument("tenant")
    ap.add_argument("label", nargs="?")
    ap.add_argument("value", nargs="?")
    ap.add_argument("--why")
    a = ap.parse_args()
    pend = pending(a.tenant)
    if a.action == "show":
        print(json.dumps(pend, indent=2, ensure_ascii=False))
        return 0
    label = norm(a.label or "")
    q = next((q for q in pend["questions"] if q.get("label") == label), None)
    if not q:
        sys.exit(f"{label!r} is not in {a.tenant}'s pending.json (copy the label exactly)")
    data = json.loads(ANSWERS.read_text())
    book = data.setdefault("by_question", {}).setdefault(a.tenant, {})
    if a.action == "yours":
        book[label] = {"value": "__USER__", "why": "left for the applicant"}
    else:
        if not a.value or not a.why:
            sys.exit("set needs an option and --why")
        offered = [o for o in (q.get("options") or []) if not o.startswith("(nested")]
        if offered and a.value not in offered and not q["type"] == "prompt":
            sys.exit(f"{a.value!r} is not one of the offered options: {offered}")
        book[label] = {"value": a.value, "why": a.why}
    ANSWERS.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"{a.tenant}: {label!r} -> {book[label]['value']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
