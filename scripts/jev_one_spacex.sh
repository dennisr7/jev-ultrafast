#!/bin/bash
# Re-run ONE SpaceX application from a fresh form (2026-10-16): close its old tabs, prepare, fill, verify, submit.
# Usage: scripts/jev_one_spacex.sh ID   -> prints "SUBMIT <utc> <id>: <result>" or "HELD <id>: <reason>"
cd "$(dirname "$0")/.." || exit 1
id=$1
uv run python - "$id" <<'PY'
import sys
from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp
ensure_daemon()
for t in cdp('Target.getTargets')['targetInfos']:
    if t['type']=='page' and f"spacex/jobs/{sys.argv[1]}" in t['url']:
        cdp('Target.closeTarget', targetId=t['targetId'])
PY
uv run python scripts/jev_prepare.py spacex "$id" >/dev/null 2>&1
NOFILL= scripts/jev_batch_spacex.sh "$id" 2>&1 | grep -E "^(SUBMIT|HELD|\[ESCALATE|\[READY)" | cut -c1-200
