#!/bin/bash
# Fill, verify and submit a list of SpaceX runs in chunks (2026-10-16). Usage: scripts/jev_batch_spacex.sh ID [ID ...]
# A run is submitted only if jev_check_runs.py says [OK] AND the key answers read back from the live form match.
cd "$(dirname "$0")/.." || exit 1
LOG=artifacts/spacex/batch.log
KEYS='How did you hear|GPA \(Under|ACT Score|Active Security|SpaceX & SpaceXAI|authorized to work in the Uni|Citizenship'
expect() {  # every expected value must appear in the --show line
  for want in "Careers site" "Not applicable/Do not recall" "33 out of 36" "Never held a clearance" \
              "I have never worked for SpaceX" "I am authorized to work in the United States for any employe" \
              "(a) U.S. citizen"; do
    grep -qF "$want" <<<"$1" || { echo "missing: $want"; return 1; }
  done
}
ids=("$@")
for ((i=0; i<${#ids[@]}; i+=12)); do
  chunk=("${ids[@]:i:12}")
  runs=(); for id in "${chunk[@]}"; do runs+=("artifacts/spacex/$id"); done
  echo "== chunk $((i/12+1)): ${chunk[*]}" | tee -a "$LOG"
  [ -z "$NOFILL" ] && uv run --env-file .env python scripts/jev_autoreview.py "${runs[@]}" --parallel 3 2>&1 | grep -E "READY|ESCALATE" | cut -c1-200 | tee -a "$LOG"
  for id in "${chunk[@]}"; do
    run="artifacts/spacex/$id"
    chk=$(uv run python scripts/jev_check_runs.py "$run" 2>&1 | head -1)
    if [[ "$chk" != "[OK]"* ]]; then echo "HELD $id: $chk" | tee -a "$LOG"; continue; fi
    show=$(uv run python scripts/jev_finish.py "$run" --show "$KEYS" 2>&1 | tail -1)
    if ! why=$(expect "$show"); then echo "HELD $id: $why" | tee -a "$LOG"; continue; fi
    t0=$(date -u +%H:%M:%S)
    res=$(uv run python scripts/jev_finish.py "$run" --submit 2>&1 | tail -1)
    echo "SUBMIT ${t0}Z $id: $res" | tee -a "$LOG"
    sleep $((35 + RANDOM % 25))
  done
done
echo "== batch done" | tee -a "$LOG"
