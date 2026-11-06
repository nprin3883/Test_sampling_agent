# AI-Defined Test Sampling - scenario 1 package

Deployable package for the AI xDLC scenario **AI-Defined Test Sampling for Source System
Migration** (Data Engineering). The agent turns specifications, code and profiling statistics into
risk-ranked business scenarios and a sampling specification; humans approve it; the engineer
extracts; the agent verifies the result.

Everything here is **synthetic**. Never commit client data, extracts or credentials.

## What is in the box

| Path | Purpose |
|---|---|
| `skill/test-sampling-agent/` | The agent as a Claude skill (instructions, references) |
| `src/sampling_validator/` | Deterministic checks and the sample verifier (Python stdlib only) |
| `tests/` | 142 tests grouped in 16 scenarios (TS-01..TS-16) and a synthetic example run |
| `evaluation/` | Templates for the LLM-vs-agent evaluation (real data goes in `evaluation/data/`, git-ignored) |
| `scripts/` | `run_scenarios.sh`, `build_skill.py` |
| `.gitlab-ci.yml`, `ci/` | GitLab pipeline: lint, test, security, package |
| `.github/workflows/ci-sampling.yml` | GitHub Actions equivalent, ready for the move |
| `docs/` | `TEST_SCENARIOS.md`, `CI_SETUP.md`, `EVALUATION_PROTOCOL.md` |

## Run it locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

make ci-local        # lint + tests with the 80% coverage gate + skill build
make scenarios       # TS-01..TS-16 one by one, pass/fail table
make example         # validate the synthetic example run
```

Without `make`:

```bash
export PYTHONPATH=src
ruff check src tests scripts skill
python3 -m pytest --cov=src/sampling_validator --cov-report=term-missing --cov-fail-under=80
bash scripts/run_scenarios.sh            # all scenarios
bash scripts/run_scenarios.sh ts09 ts10  # selected scenarios
python3 -m pytest -m ts09 -q             # one scenario
python3 -m sampling_validator.cli check-run tests/fixtures/good_run
```

More commands, including how to break the example on purpose, are in `docs/TEST_SCENARIOS.md`.

## Use the validators on a real run

Keep one folder per migration: `request_pack.json`, `sampling_brief.json`, `sampling_spec.json`,
`coverage_report.json` and `sample/` (masked CSV, one per table). Check what exists so far:

```bash
export PYTHONPATH=src
python3 -m sampling_validator.cli check-run path/to/run
```

Exit code 0 = no errors, 1 = errors found, 2 = unreadable input. Add `--json` before the command for
machine-readable output.

## Evaluate the agent against a general-purpose LLM

`docs/EVALUATION_PROTOCOL.md` describes the proposed head-to-head study: design, procedure,
criteria, formulas and the success rule. `python3 -m sampling_validator.cli evaluate <folder>`
scores it and refuses to give a verdict until the thresholds are agreed. The study has not been run:
the only data in the repository is invented and flagged as illustrative.

## Deploy

1. **GitLab now**: follow `docs/CI_SETUP.md` (variables, runner probe, first run).
2. **GitHub later**: push the same repository; `.github/workflows/ci-sampling.yml` is already there.
   The secrets to create are listed in `docs/CI_SETUP.md`.
3. **Skill**: `make skill` builds `dist/test-sampling-agent.skill`; upload it to your Claude workspace (skills section of the settings).

## Scope and limits

- The validators check **structure, consistency and the card's rules**. They do not judge whether a
  scenario list is complete for your business; that remains the Data Architect's review in step 4.
- The personal-data scan (DAT-001, DAT-002) is a heuristic. It does not replace the data-handling
  rules or the masking policy of the client.
- Out of scope, as in the card: test cases and expected results, synthetic data generation, running
  the extraction, volume or performance datasets.
