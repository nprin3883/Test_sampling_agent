# Test scenarios

Each scenario proves one rule of the card. Every scenario has a positive case (a valid artifact is
accepted) and negative cases (a broken artifact is rejected with a specific finding code).

| ID | Card step | What it proves | Rejected with | Command |
|---|---|---|---|---|
| TS-01 | 1 | Request pack has everything the agent needs | REQ-001..004 (REQ-005 warns: no code) | `python3 -m pytest -m ts01 -q` |
| TS-02 | 2 | Brief works on schemas, statistics, code; never raw records | BRF-001, BRF-005 | `python3 -m pytest -m ts02 -q` |
| TS-03 | 2 | Gaps surface as questions; rules carry evidence | BRF-002, BRF-003 | `python3 -m pytest -m ts03 -q` |
| TS-04 | 2 | No code means reduced confidence | BRF-004, BRF-006 | `python3 -m pytest -m ts04 -q` |
| TS-05 | 3 | Scenarios complete, risk-ranked; every edge category present or justified | SPC-001, 002, 004, 005 | `python3 -m pytest -m ts05 -q` |
| TS-06 | 3 | Coverage gaps are explicit and consistent | SPC-003, 012 | `python3 -m pytest -m ts06 -q` |
| TS-07 | 3 | Fits the size limit; related tables stay consistent; traceable to rules | SPC-006, 007, 009, 010 | `python3 -m pytest -m ts07 -q` |
| TS-08 | 3 | The agent drafts read-only queries and never runs them | SPC-008 | `python3 -m pytest -m ts08 -q` |
| TS-09 | 4 | Named humans approve; masking confirmed; no self-approval; extraction waits | SPC-011, 013 | `python3 -m pytest -m ts09 -q` |
| TS-10 | 5 | Sample is checked for coverage, volume and referential integrity | COV-001, 002, 003 | `python3 -m pytest -m ts10 -q` |
| TS-11 | 5 | Reported numbers are reproducible from the sample | COV-004..009 | `python3 -m pytest -m ts11 -q` |
| TS-12 | all | No personal data in artifacts; extracted sample is masked | DAT-001, DAT-002 | `python3 -m pytest -m ts12 -q` |
| TS-13 | all | The command line works end to end, with correct exit codes | exit 1 / 2 | `python3 -m pytest -m ts13 -q` |
| TS-14 | - | The skill is valid, self-contained and runs from a clean unzip | - | `python3 -m pytest -m ts14 -q` |

Run all of them with a result table: `bash scripts/run_scenarios.sh`.

## See a failure with your own eyes

```bash
export PYTHONPATH=src
cp -r tests/fixtures/good_run /tmp/run

# 1. baseline: passes
python3 -m sampling_validator.cli check-run /tmp/run

# 2. the agent approves its own specification -> SPC-011
sed -i 's/"data_architect": "A. Example"/"data_architect": "Claude"/' /tmp/run/sampling_spec.json
python3 -m sampling_validator.cli check-run /tmp/run; echo "exit code: $?"
cp tests/fixtures/good_run/sampling_spec.json /tmp/run/

# 3. the extracted sample loses its late-arriving orders -> the old report no longer matches (COV-008)
sed -i '/^O013,/d;/^O027,/d' /tmp/run/sample/CUSTOMER_ORDER.csv
python3 -m sampling_validator.cli check-run /tmp/run

# 4. recompute the report honestly -> scenario S06 is missing (COV-002)
python3 -m sampling_validator.cli verify --spec /tmp/run/sampling_spec.json \
  --sample-dir /tmp/run/sample --ticket DEMO-123 --out /tmp/run/coverage_report.json
```

## The synthetic example

`tests/fixtures/good_run/` is a fictional legacy CRM migration (customers and orders): 6 business
rules, 9 scenarios (8 covered, 1 declared gap), a 48-row masked sample. It is also bundled in the
skill as `assets/example_run/` so the agent can imitate its shape.
