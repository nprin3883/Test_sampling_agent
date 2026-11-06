"""Scenarios TS-15 and TS-16: scoring the agent against a general-purpose LLM."""
import json
import shutil
from pathlib import Path

import pytest

from helpers import FIXTURES, run_cli, write_json
from sampling_validator import evaluation

EXAMPLE = FIXTURES / "evaluation_example"


def run_doc(case, name):
    return json.loads((EXAMPLE / "cases" / case / "runs" / f"{name}.json").read_text("utf-8"))


def ref_doc(case):
    return json.loads((EXAMPLE / "cases" / case / "reference_scenarios.json").read_text("utf-8"))


def copy_example(tmp_path):
    dst = Path(tmp_path) / "eval"
    shutil.copytree(EXAMPLE, dst)
    return dst


def edit(root, relative, change):
    path = root / relative
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    write_json(path, doc)


def codes_of(result):
    return {f.code for f in result["findings"] if f.severity == "error"}


@pytest.mark.ts15
def test_ts15_run_score_matches_hand_calculation():
    score = evaluation.score_run(run_doc("CASE-A", "A-LLM-1"), ref_doc("CASE-A"))
    assert round(score["weighted_coverage"], 4) == round(9 / 17, 4)
    assert score["critical_misses"] == 1
    assert round(score["precision"], 4) == round(4 / 6, 4)
    assert score["gap_honesty"] == 0.0
    assert score["effort_minutes"] == 75
    assert round(score["coverage_per_hour"], 4) == round((9 / 17) / (75 / 60), 4)


@pytest.mark.ts15
def test_ts15_complete_and_honest_run_scores_the_maximum():
    score = evaluation.score_run(run_doc("CASE-A", "A-AGT-2"), ref_doc("CASE-A"))
    assert score["weighted_coverage"] == 1.0
    assert score["critical_misses"] == 0
    assert score["precision"] == 1.0
    assert score["gap_honesty"] == 1.0


@pytest.mark.ts15
def test_ts15_declared_gap_counts_as_honesty():
    score = evaluation.score_run(run_doc("CASE-A", "A-AGT-1"), ref_doc("CASE-A"))
    assert round(score["weighted_coverage"], 4) == round(16 / 17, 4)
    assert score["gap_honesty"] == 1.0


@pytest.mark.ts15
def test_ts15_zero_effort_has_no_coverage_per_hour():
    run = dict(run_doc("CASE-A", "A-AGT-2"), time_to_approval_min=0, reviewer_minutes=0)
    assert evaluation.score_run(run, ref_doc("CASE-A"))["coverage_per_hour"] is None


@pytest.mark.ts15
def test_ts15_summary_uses_medians_per_case_and_overall():
    result = evaluation.evaluate(EXAMPLE)
    assert result["n_runs"] == 8
    case_a = result["per_case"]["CASE-A"]
    assert round(case_a["agent"]["weighted_coverage"], 4) == round((16 / 17 + 1.0) / 2, 4)
    assert case_a["general_llm"]["critical_misses"] == 0.5
    assert case_a["general_llm"]["effort_minutes"] == 70
    overall = result["overall"]["general_llm"]["effort_minutes"]
    assert overall == (70 + 77.5) / 2


@pytest.mark.ts15
def test_ts15_agreed_thresholds_give_a_verdict_with_three_rules():
    verdict = evaluation.evaluate(EXAMPLE)["verdict"]
    assert verdict["status"] == "PASS"
    assert [r["ok"] for r in verdict["rules"]] == [True, True, True]


@pytest.mark.ts15
@pytest.mark.parametrize("change", [
    lambda th: th.update(min_coverage_gain=0.9),
    lambda th: th.update(max_critical_misses=-1),
    lambda th: th.update(max_effort_ratio=0.1),
], ids=["gain-too-small", "too-many-misses", "too-much-effort"])
def test_ts15_each_rule_can_fail_the_verdict(tmp_path, change):
    root = copy_example(tmp_path)
    edit(root, "thresholds.json", change)
    verdict = evaluation.evaluate(root)["verdict"]
    assert verdict["status"] == "FAIL"
    assert [r["ok"] for r in verdict["rules"]].count(False) == 1


@pytest.mark.ts15
def test_ts15_report_shows_both_arms_and_every_case():
    report = evaluation.render_report(evaluation.evaluate(EXAMPLE))
    for text in ("## Verdict: PASS", "## Case CASE-A", "## Case CASE-B", "## Overall",
                 "general_llm", "agent", "Weighted coverage", "Coverage per hour of effort"):
        assert text in report


@pytest.mark.ts16
@pytest.mark.parametrize("change", [
    lambda th: th.pop("agreed_by"),
    lambda th: th.update(agreed_on=""),
], ids=["no-agreed-by", "no-agreed-on"])
def test_ts16_no_verdict_before_the_thresholds_are_agreed(tmp_path, change):
    root = copy_example(tmp_path)
    edit(root, "thresholds.json", change)
    result = evaluation.evaluate(root)
    assert result["verdict"]["status"] == "NOT_EVALUABLE"
    assert result["verdict"]["rules"] == []
    assert any(f.code == "EVL-009" and f.severity == "warning" for f in result["findings"])


@pytest.mark.ts16
def test_ts16_both_arms_are_needed_for_a_verdict(tmp_path):
    root = copy_example(tmp_path)
    for path in (root / "cases").glob("*/runs/*-AGT-*.json"):
        edit(root, path.relative_to(root), lambda r: r.update(arm="baseline"))
    verdict = evaluation.evaluate(root)["verdict"]
    assert verdict["status"] == "NOT_EVALUABLE"


@pytest.mark.ts16
@pytest.mark.parametrize("change, expected", [
    (lambda r: r.pop("arm"), "EVL-003"),
    (lambda r: r.update(arm="human"), "EVL-004"),
    (lambda r: r.update(covered_reference_ids=["R99"]), "EVL-005"),
    (lambda r: r.update(declared_gap_ids=["R99"]), "EVL-005"),
    (lambda r: r["proposed_scenarios"][0].update(reference_id="R99"), "EVL-005"),
    (lambda r: r.update(time_to_approval_min=-5), "EVL-006"),
    (lambda r: r.update(iterations=0), "EVL-006"),
    (lambda r: r.update(sample_size_rows=1.5), "EVL-006"),
    (lambda r: r.update(validators_pass="yes"), "EVL-006"),
    (lambda r: r.update(covered_reference_ids="R01"), "EVL-006"),
    (lambda r: r.update(case_id="CASE-B"), "EVL-007"),
    (lambda r: r.update(proposed_scenarios=[]), "EVL-010"),
], ids=["no-arm", "bad-arm", "unknown-covered", "unknown-gap", "unknown-proposed", "negative-time",
        "zero-iterations", "fractional-rows", "validators-not-bool", "ids-not-list",
        "wrong-case", "nothing-proposed"])
def test_ts16_invalid_run_results_are_rejected(tmp_path, change, expected):
    root = copy_example(tmp_path)
    edit(root, "cases/CASE-A/runs/A-LLM-1.json", change)
    assert expected in codes_of(evaluation.evaluate(root))


@pytest.mark.ts16
def test_ts16_duplicate_run_ids_and_bad_references_are_rejected(tmp_path):
    root = copy_example(tmp_path)
    shutil.copy(root / "cases/CASE-A/runs/A-LLM-1.json", root / "cases/CASE-A/runs/copy.json")
    assert "EVL-008" in codes_of(evaluation.evaluate(root))
    ref_b = "cases/CASE-B/reference_scenarios.json"
    edit(root, ref_b, lambda r: r["scenarios"][1].update(id="B01"))
    assert "EVL-002" in codes_of(evaluation.evaluate(root))
    edit(root, ref_b, lambda r: r["scenarios"][0].update(risk="x"))
    assert "EVL-002" in codes_of(evaluation.evaluate(root))
    edit(root, ref_b, lambda r: r.pop("scenarios"))
    assert "EVL-001" in codes_of(evaluation.evaluate(root))
    assert evaluation.check_reference([]) and evaluation.check_run([], set(), "C")


@pytest.mark.ts16
def test_ts16_missing_inputs_are_reported(tmp_path):
    root = copy_example(tmp_path)
    (root / "thresholds.json").unlink()
    assert "EVL-009" in codes_of(evaluation.evaluate(root))
    (root / "cases/CASE-A/reference_scenarios.json").unlink()
    assert "EVL-001" in codes_of(evaluation.evaluate(root))
    empty = Path(tmp_path) / "empty"
    empty.mkdir()
    assert "EVL-001" in codes_of(evaluation.evaluate(empty))


@pytest.mark.ts16
def test_ts16_thresholds_must_be_numbers(tmp_path):
    root = copy_example(tmp_path)
    edit(root, "thresholds.json", lambda th: th.update(max_effort_ratio=None))
    result = evaluation.evaluate(root)
    assert "EVL-009" in codes_of(result)
    assert result["verdict"]["status"] == "NOT_EVALUABLE"
    assert evaluation.check_thresholds("text")


@pytest.mark.ts16
def test_ts16_example_data_is_flagged_as_not_real_results(tmp_path):
    result = evaluation.evaluate(EXAMPLE)
    assert result["illustrative"] is True
    assert evaluation.render_report(result).startswith(
        "# Evaluation report: general-purpose LLM vs specialist agent\n\n> ILLUSTRATIVE DATA")
    root = copy_example(tmp_path)
    for path in root.rglob("*.json"):
        edit(root, path.relative_to(root), lambda d: d.pop("_illustrative"))
    clean = evaluation.evaluate(root)
    assert clean["illustrative"] is False
    assert "ILLUSTRATIVE" not in evaluation.render_report(clean)


@pytest.mark.ts16
def test_ts16_personal_data_in_a_run_file_is_rejected(tmp_path):
    root = copy_example(tmp_path)
    edit(root, "cases/CASE-A/runs/A-LLM-1.json",
         lambda r: r.update(engineer="jane.doe@client-corp.com"))
    assert "DAT-001" in codes_of(evaluation.evaluate(root))


@pytest.mark.ts16
def test_ts16_templates_are_valid_json_and_not_agreed():
    templates = Path(__file__).resolve().parent.parent / "evaluation" / "templates"
    th = json.loads((templates / "thresholds.json").read_text("utf-8"))
    assert evaluation.thresholds_agreed(th) is False
    ref = json.loads((templates / "reference_scenarios.json").read_text("utf-8"))
    assert evaluation.check_reference(ref)  # the blank template must not pass as filled in
    run = json.loads((templates / "run_result.json").read_text("utf-8"))
    assert all(k in run for k in evaluation.RUN_FIELDS)


@pytest.mark.ts16
def test_ts16_command_line_prints_writes_and_signals_errors(tmp_path):
    code, out, _ = run_cli("evaluate", EXAMPLE)
    assert code == 0 and "## Verdict: PASS" in out and "ILLUSTRATIVE DATA" in out
    report = Path(tmp_path) / "report.md"
    assert run_cli("evaluate", EXAMPLE, "--out", report)[0] == 0
    assert report.read_text("utf-8").startswith("# Evaluation report")
    code, out, _ = run_cli("--json", "evaluate", EXAMPLE)
    assert code == 0 and json.loads(out)["verdict"]["status"] == "PASS"
    root = copy_example(tmp_path)
    edit(root, "cases/CASE-A/runs/A-LLM-1.json", lambda r: r.update(arm="human"))
    code, out, _ = run_cli("evaluate", root)
    assert code == 1 and "EVL-004" in out


@pytest.mark.ts15
def test_ts15_median_resists_an_outlier_run(tmp_path):
    root = copy_example(tmp_path)
    outlier = run_doc("CASE-A", "A-LLM-1")
    outlier.update(run_id="A-LLM-3", covered_reference_ids=[s["id"] for s in ref_doc("CASE-A")[
        "scenarios"]])
    write_json(root / "cases/CASE-A/runs/A-LLM-3.json", outlier)
    case_a = evaluation.evaluate(root)["per_case"]["CASE-A"]["general_llm"]
    # runs cover 9/17, 11/17 and 17/17: the median is 11/17, the mean would be higher
    assert round(case_a["weighted_coverage"], 4) == round(11 / 17, 4)


@pytest.mark.ts16
@pytest.mark.parametrize("where", [
    "thresholds.json", "cases/CASE-A/reference_scenarios.json", "cases/CASE-A/runs/A-AGT-1.json",
], ids=["thresholds", "reference", "run"])
def test_ts16_any_flagged_file_marks_the_whole_report_as_illustrative(tmp_path, where):
    root = copy_example(tmp_path)
    for path in root.rglob("*.json"):
        if path.relative_to(root).as_posix() != where:
            edit(root, path.relative_to(root), lambda d: d.pop("_illustrative"))
    assert evaluation.evaluate(root)["illustrative"] is True
