PYTHON ?= python3
export PYTHONPATH := src

.PHONY: install lint test scenarios example evaluate-demo skill ci-local clean

install:  ## install dev tooling (pytest, pytest-cov, ruff)
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:  ## style and static checks
	ruff check src tests scripts skill

test:  ## full test suite with the 80% coverage gate
	$(PYTHON) -m pytest --cov=src/sampling_validator --cov-report=term-missing \
		--cov-report=xml:coverage.xml --junitxml=report.xml --cov-fail-under=80

scenarios:  ## run test scenarios TS-01..TS-16 one by one
	bash scripts/run_scenarios.sh

example:  ## validate the bundled synthetic example run
	$(PYTHON) -m sampling_validator.cli check-run tests/fixtures/good_run

evaluate-demo:  ## score the invented, illustrative evaluation example
	$(PYTHON) -m sampling_validator.cli evaluate tests/fixtures/evaluation_example

skill:  ## build dist/test-sampling-agent.skill
	$(PYTHON) scripts/build_skill.py --out dist

ci-local: lint test skill  ## what the pipeline runs, minus the security scanners

clean:
	rm -rf dist .cache .pytest_cache .ruff_cache .coverage coverage.xml report.xml
