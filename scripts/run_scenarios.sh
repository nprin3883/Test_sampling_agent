#!/usr/bin/env bash
# Run the test scenarios TS-01..TS-16 one by one and print a pass/fail table.
# Usage: scripts/run_scenarios.sh            # all scenarios
#        scripts/run_scenarios.sh ts09 ts10  # selected scenarios
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"

DESCRIPTIONS=(
  "ts01|Request pack is complete (step 1)"
  "ts02|Brief works on metadata, never raw records (step 2)"
  "ts03|Brief surfaces gaps instead of inventing (step 2)"
  "ts04|Missing source code lowers confidence (step 2)"
  "ts05|Scenarios complete, risk-ranked, edge categories covered (step 3)"
  "ts06|Coverage gaps are explicit (step 3)"
  "ts07|Volume limit, relationships, traceability (step 3)"
  "ts08|Extraction queries are read-only drafts (step 3)"
  "ts09|Human approval gate (step 4)"
  "ts10|Sample verified against the specification (step 5)"
  "ts11|Reported numbers are reproducible (step 5)"
  "ts12|No personal data in artifacts or samples"
  "ts13|Command line end to end"
  "ts14|Skill package valid and self-contained"
  "ts15|Evaluation scoring: agent vs general-purpose LLM"
  "ts16|Evaluation protocol integrity: thresholds, inputs, flags"
)

selected=("$@")
failed=0
printf '%-6s %-62s %s\n' "ID" "Scenario" "Result"
for entry in "${DESCRIPTIONS[@]}"; do
  id="${entry%%|*}"; label="${entry#*|}"
  if [ ${#selected[@]} -gt 0 ] && [[ ! " ${selected[*]} " == *" $id "* ]]; then continue; fi
  log="$(mktemp)"
  if "$PYTHON" -m pytest -m "$id" -q >"$log" 2>&1; then result="PASS"; else result="FAIL"; failed=1; fi
  printf '%-6s %-62s %s  (%s)\n' "$id" "$label" "$result" "$(tail -n 1 "$log")"
  if [ "$result" = "FAIL" ]; then sed 's/^/        /' "$log"; fi
  rm -f "$log"
done
[ "$failed" -eq 0 ] && echo "ALL SCENARIOS PASSED" || echo "SOME SCENARIOS FAILED"
exit "$failed"
