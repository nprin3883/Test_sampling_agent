# Evaluation protocol: general-purpose LLM vs specialist agent

**Status: proposed. No head-to-head results exist yet.** The example data in
`tests/fixtures/evaluation_example/` is invented to test the scoring tool and is flagged
`_illustrative`; it says nothing about how the agent performs.

The automated tests (TS-01 to TS-14) prove that the validators behave correctly. This protocol is
different: it measures whether the agent helps engineers produce better samples than they would
with a general-purpose LLM.

## 1. Question and hypothesis

Does an engineer using the specialist agent reach a higher, risk-weighted scenario coverage, with
fewer critical misses, at equal or lower effort than an engineer using a general-purpose LLM?
This is the hypothesis of the scenario card, with the general-purpose LLM as the comparison.

## 2. Design

| Arm | Who works with what |
|---|---|
| A, `general_llm` | An engineer with a general-purpose LLM chat and free prompting. No skill, no validators. |
| B, `agent` | An engineer with the sampling agent: the skill, its five-step workflow and the validators. |
| C, `baseline` (optional) | Today's practice: a top-N or random sample, scored with the same criteria. |

Both arms get the same inputs (request pack, schemas, profiling statistics, source code), the same
time box and the same Data Architect as reviewer. Nobody works on raw production data: samples are
masked and extracted only in the authorised environment.

## 3. Procedure

1. **Frame.** Pick 2 to 3 migration cases of different complexity. For each, the Data Architect
   writes the reference scenario list (`reference_scenarios.json`, with a risk level per scenario)
   **before any run** and keeps it hidden from the engineers.
2. **Run.** Each engineer works on a given case in one arm only. Rotate cases and arms so every
   engineer uses both arms and every case is tried in both. Example with two engineers E1, E2 and two
   cases A, B: E1 does A with the general LLM then B with the agent; E2 does A with the agent then B
   with the general LLM.
3. **Extract.** The engineer runs the approved queries and produces a masked sample, in every arm.
4. **Score.** Put each output in the sampling-specification template, so the scorer cannot tell the
   arm from the format. The Data Architect marks which reference scenarios the extracted sample
   covers and which proposed scenarios match a reference one. Keep the run-to-arm key separately
   and fill the `arm` field only after all scoring is done. Run the validators on each output. The
   scorer also logs time, iterations and reviewer minutes.
5. **Compare.** Run the scoring tool (section 6) and read the report case by case.

## 4. Criteria

Reference scenario weights: high = 3, medium = 2, low = 1.

| Family | Criterion | Definition |
|---|---|---|
| Effectiveness | Weighted coverage | Weights of the reference scenarios present in the extracted sample / weights of all reference scenarios |
| Effectiveness | Critical misses | Number of high-risk reference scenarios absent from the sample |
| Effectiveness | Precision | Proposed scenarios that match a reference scenario / all proposed scenarios |
| Effectiveness | Gap honesty | Uncovered reference scenarios that the arm declared as gaps / uncovered reference scenarios (1 if none) |
| Effectiveness | Validators pass | The sampling validators accept the output (1 or 0) |
| Efficiency | Time to approval | Minutes from request pack to an approved specification |
| Efficiency | Iterations | Review rounds plus re-extractions (at least 1) |
| Efficiency | Sample size | Rows in the extracted sample |
| Efficiency | Reviewer effort | Minutes the Data Architect spends reviewing and correcting |
| Efficiency | Total effort | Time to approval + reviewer effort |
| Combined | Coverage per hour | Weighted coverage / total effort in hours |

Aggregation: the median of the runs per case and arm, then the median of the case medians.
Token and licence cost may be noted (`cost` fields are allowed) but do not enter the verdict.

## 5. Success rule and thresholds

The tool gives a verdict only if the thresholds were agreed before the first run. The rule has three
parts, all of which must hold (agent medians against general-LLM medians):

1. coverage gain (agent minus general LLM) is at least `min_coverage_gain`
2. critical misses of the agent are at most `max_critical_misses`
3. effort ratio (agent / general LLM) is at most `max_effort_ratio`

Copy `evaluation/templates/thresholds.json`, agree the three values with the Data Architect, and
fill `agreed_by` and `agreed_on`. The template ships **without** values on purpose. Without them the
verdict is `NOT_EVALUABLE`.

## 6. Running the scoring tool

Folder layout (real data goes under `evaluation/data/`, which git ignores):

```
evaluation/data/<study>/
  thresholds.json
  cases/<case_id>/reference_scenarios.json
  cases/<case_id>/runs/<run_id>.json
```

```bash
export PYTHONPATH=src
python3 -m sampling_validator.cli evaluate evaluation/data/<study> --out report.md
python3 -m sampling_validator.cli evaluate tests/fixtures/evaluation_example   # illustrative demo
```

Exit code 0 = inputs valid (the report may still say FAIL or NOT_EVALUABLE), 1 = invalid inputs
(finding codes EVL-001 to EVL-010, DAT-001), 2 = unreadable file. Templates are in
`evaluation/templates/`. Use pseudonyms for engineers (E1, E2): names and e-mail addresses are
rejected by the personal-data check.

## 7. Limits

- With 2 to 3 cases and a few engineers, the report gives medians and spread, not statistical
  significance. Fewer than 2 cases is flagged as an indication only.
- Scoring depends on the Data Architect's judgement. Blind scoring reduces, but does not remove, bias.
- A general-purpose LLM result depends on the model, its version and the prompt. Record them in the
  run notes so the comparison can be repeated.
- A learning effect remains even with rotation: engineers get better at the task over the study.
- Real case data (reference lists, extracts) may be client-confidential. Keep it out of this
  repository, or anonymise it first.
