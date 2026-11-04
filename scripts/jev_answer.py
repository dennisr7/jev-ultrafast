"""Answer a paused `jev_task.py --step` run, then print what it did next.

python scripts/jev_answer.py go|skip|stop|wait [--output artifacts/jev_task] [--timeout 60]

`wait` answers nothing; it only waits for the next decision or result. Needs no Jev dependencies.
"""

import argparse
import json
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("answer", choices=["go", "skip", "stop", "wait"])
parser.add_argument("--output", default="artifacts/jev_task")
parser.add_argument("--timeout", type=float, default=60)
args = parser.parse_args()

output = Path(args.output)
log = output / "log.jsonl"
seen = len(log.read_text().splitlines()) if log.exists() else 0
if args.answer != "wait":
    (output / "control").write_text(args.answer)
    seen = len(log.read_text().splitlines())
new = []
deadline = time.monotonic() + args.timeout
while time.monotonic() < deadline:
    lines = log.read_text().splitlines() if log.exists() else []
    new = [json.loads(line) for line in lines[seen:] if line.startswith("{")]
    # `wait` returns the pending decision if one is already showing.
    if args.answer == "wait" and not new and lines:
        new = [json.loads(lines[-1])] if json.loads(lines[-1])["event"] in {"decision", "result"} else []
    if any(e["event"] in {"decision", "result"} for e in new):
        break
    time.sleep(0.2)
for event in new:
    if event["event"] == "result":  # Page text and history stay in result.json.
        event = {k: v for k, v in event.items() if k not in {"final_text", "history"}}
    print(json.dumps(event))
if not new:
    print(json.dumps({"event": "timeout", "note": "No new decision or result yet; the run may still be working."}))
