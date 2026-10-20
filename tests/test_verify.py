"""Scenarios TS-10 to TS-12: verifying the extracted sample (step 5) and protecting data."""
import copy

import pytest

from helpers import GOOD, error_codes, mutated, report, spec
from sampling_validator import checks, data_guard, verify_sample

TICKET = "DEMO-123"


def sample():
    return verify_sample.load_sample(GOOD / "sample")


def verified(change=None, spec_doc=None):
    """Build the report for a (modified) sample and return its findings and report."""
    smp = sample()
    if change:
        change(smp)
    doc = spec_doc or spec()
    rep = verify_sample.build_report(doc, smp, TICKET)
    return error_codes(checks.check_coverage_report(rep, doc)), rep


@pytest.mark.ts10
def test_ts10_good_sample_covers_everything_the_specification_promised():
    codes, rep = verified()
    assert codes == set()
    assert rep["total_rows"] == 48
    assert rep["summary"] == {"covered": ["S%02d" % i for i in range(1, 9)], "missed": [],
                              "declared_gaps": ["S09"]}


@pytest.mark.ts10
def test_ts10_missing_scenario_in_the_sample_is_reported():
    def change(smp):
        smp["CUSTOMER_ORDER"] = [r for r in smp["CUSTOMER_ORDER"] if int(r["LOAD_LAG_DAYS"]) <= 2]
    codes, rep = verified(change)
    assert "COV-002" in codes
    assert rep["summary"]["missed"] == ["S06"]


@pytest.mark.ts10
def test_ts10_orphan_child_rows_break_referential_integrity():
    def change(smp):
        orphan = dict(smp["CUSTOMER_ORDER"][0], ORDER_ID="O999", CUSTOMER_ID="C999")
        smp["CUSTOMER_ORDER"].append(orphan)
    codes, rep = verified(change)
    assert "COV-003" in codes
    assert rep["referential_integrity"]["ok"] is False


@pytest.mark.ts10
def test_ts10_sample_above_the_volume_limit_is_rejected():
    codes, rep = verified(spec_doc=mutated(spec, lambda s: s["sampling_strategy"].update(
        max_sample_rows=30)))
    assert "COV-001" in codes
    assert rep["volume_limit"]["ok"] is False


@pytest.mark.ts10
def test_ts10_missing_table_file_means_missing_scenarios():
    def change(smp):
        del smp["CUSTOMER_ORDER"]
    codes, _ = verified(change)
    assert "COV-002" in codes


ROWS = [{"A": "1", "B": "x"}, {"A": "2", "B": ""}, {"A": "3", "B": "x"}, {"A": "10", "B": "y"}]


@pytest.mark.ts10
@pytest.mark.parametrize("cond, expected", [
    ({"field": "B", "op": "is_null"}, 1),
    ({"field": "B", "op": "not_null"}, 3),
    ({"field": "A", "op": "eq", "value": "2"}, 1),
    ({"field": "B", "op": "ne", "value": "x"}, 1),
    ({"field": "B", "op": "in", "value": ["x", "y"]}, 3),
    ({"field": "A", "op": "between", "value": [2, 3]}, 2),
    ({"field": "A", "op": "lt", "value": 3}, 2),
    ({"field": "A", "op": "lte", "value": 3}, 3),
    ({"field": "A", "op": "gt", "value": 3}, 1),
    ({"field": "A", "op": "gte", "value": 3}, 2),
    ({"field": "B", "op": "duplicate"}, 2),
    ({"field": "B", "op": "gt", "value": 3}, 0),
    ({"field": "B", "op": "between", "value": [1, 2]}, 0),
], ids=["is_null", "not_null", "eq", "ne", "in", "between", "lt", "lte", "gt", "gte",
        "duplicate", "text-vs-number", "text-between"])
def test_ts10_match_operators(cond, expected):
    match = {"table": "T", "conditions": [cond]}
    assert verify_sample.count_matches({"T": ROWS}, match) == expected


@pytest.mark.ts10
def test_ts10_all_conditions_must_hold_and_unknown_operators_fail_loudly():
    both = {"table": "T", "conditions": [{"field": "B", "op": "eq", "value": "x"},
                                         {"field": "A", "op": "gt", "value": 1}]}
    assert verify_sample.count_matches({"T": ROWS}, both) == 1
    bad = {"table": "T", "conditions": [{"field": "A", "op": "near", "value": 1}]}
    with pytest.raises(ValueError):
        verify_sample.count_matches({"T": ROWS}, bad)


@pytest.mark.ts11
def test_ts11_committed_report_is_reproducible_from_the_sample():
    assert verify_sample.build_report(spec(), sample(), TICKET) == report()
    rebuilt = verify_sample.build_report(spec(), sample(), TICKET)
    assert checks.compare_reports(report(), rebuilt) == []


@pytest.mark.ts11
def test_ts11_invented_coverage_numbers_are_detected():
    fake = mutated(report, lambda r: r["scenario_coverage"][5].update(matched_rows=9))
    found = checks.compare_reports(fake, verify_sample.build_report(spec(), sample(), TICKET))
    assert {f.code for f in found} == {"COV-008"}


@pytest.mark.ts11
def test_ts11_invented_row_counts_are_detected():
    fake = mutated(report, lambda r: r["rows_by_table"].update(CUSTOMER=5))
    found = checks.compare_reports(fake, verify_sample.build_report(spec(), sample(), TICKET))
    assert {f.code for f in found} == {"COV-008"}


@pytest.mark.ts11
@pytest.mark.parametrize("change, expected", [
    (lambda r: r["summary"].update(missed=["S01"]), "COV-009"),
    (lambda r: r["scenario_coverage"].pop(), "COV-006"),
    (lambda r: r.update(ticket_ref=""), "COV-005"),
    (lambda r: r.pop("summary"), "COV-007"),
], ids=["summary-inconsistent", "scenario-dropped", "no-ticket", "no-summary"])
def test_ts11_report_must_be_complete_and_consistent(change, expected):
    found = checks.check_coverage_report(mutated(report, change), spec())
    assert expected in error_codes(found)


@pytest.mark.ts11
def test_ts11_report_needs_an_approved_specification():
    draft = mutated(spec, lambda s: s.update(approval={"status": "draft"}))
    assert "COV-004" in error_codes(checks.check_coverage_report(report(), draft))
    assert error_codes(checks.check_coverage_report([], spec())) == {"COV-007"}


@pytest.mark.ts12
@pytest.mark.parametrize("text, kind", [
    ("jane.doe@client-corp.com", "e-mail address"),
    ("masked_001@example.com", None),
    ("DE89" + "370400440532013000", "IBAN-like value"),
    ("4111" * 4, "card-number-like value"),
    ("an ordinary sentence", None),
], ids=["real-email", "example-email", "iban", "card", "plain"])
def test_ts12_personal_data_patterns(text, kind):
    assert data_guard.suspicious(text) == kind


@pytest.mark.ts12
def test_ts12_good_artifacts_are_clean():
    for doc in (report(), spec()):
        assert data_guard.scan_artifact(doc) == []


@pytest.mark.ts12
def test_ts12_personal_data_inside_an_artifact_is_rejected():
    dirty = mutated(spec, lambda s: s["scenarios"][0].update(
        rationale="see jane.doe@client-corp.com"))
    assert {f.code for f in data_guard.scan_artifact(dirty)} == {"DAT-001"}


@pytest.mark.ts12
def test_ts12_raw_records_inside_an_artifact_are_rejected():
    dirty = copy.deepcopy(report())
    dirty["records"] = [{"CUSTOMER_ID": "C001"}]
    assert {f.code for f in data_guard.scan_artifact(dirty)} == {"DAT-001"}


@pytest.mark.ts12
def test_ts12_unmasked_values_in_the_extracted_sample_are_rejected():
    smp = sample()
    assert data_guard.scan_sample(smp) == []
    smp["CUSTOMER"][0]["EMAIL"] = "jane.doe@client-corp.com"
    smp["CUSTOMER"][1]["EMAIL"] = "john.roe@client-corp.com"
    found = data_guard.scan_sample(smp)
    assert [f.code for f in found] == ["DAT-002"]
    assert found[0].where == "CUSTOMER.EMAIL"
