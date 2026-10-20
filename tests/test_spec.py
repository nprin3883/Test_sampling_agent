"""Scenarios TS-05 to TS-09: the scenarios, the sampling specification and the human gate."""
import pytest

from helpers import brief, error_codes, mutated, request, spec
from sampling_validator import checks


def check(change=None, require_approved=False):
    doc = mutated(spec, change) if change else spec()
    return error_codes(checks.check_spec(doc, brief(), request(), require_approved))


@pytest.mark.ts05
def test_ts05_good_specification_is_accepted():
    assert check() == set()


@pytest.mark.ts05
def test_ts05_scenarios_must_be_ranked_by_risk():
    def change(s):
        s["scenarios"].insert(0, s["scenarios"].pop(7))
    assert "SPC-004" in check(change)


@pytest.mark.ts05
def test_ts05_edge_category_cannot_be_silently_forgotten():
    def change(s):
        s["scenarios"] = [x for x in s["scenarios"] if x["category"] != "late_arriving"]
    assert "SPC-005" in check(change)


@pytest.mark.ts05
def test_ts05_edge_category_can_be_declared_not_applicable_with_a_reason():
    def change(s):
        s["scenarios"] = [x for x in s["scenarios"] if x["category"] != "late_arriving"]
        s["edge_categories_not_applicable"] = {"late_arriving": "The source has no late loads"}
    assert check(change) == set()


@pytest.mark.ts05
def test_ts05_not_applicable_needs_a_reason():
    def change(s):
        s["scenarios"] = [x for x in s["scenarios"] if x["category"] != "late_arriving"]
        s["edge_categories_not_applicable"] = {"late_arriving": ""}
    assert "SPC-005" in check(change)


@pytest.mark.ts05
@pytest.mark.parametrize("change", [
    lambda s: s["scenarios"][0].pop("rationale"),
    lambda s: s["scenarios"][0].update(risk="critical"),
    lambda s: s["scenarios"][0].update(category="weird"),
    lambda s: s["scenarios"][0].update(covered="yes"),
], ids=["no-rationale", "bad-risk", "bad-category", "covered-not-bool"])
def test_ts05_scenario_fields_are_enforced(change):
    assert "SPC-002" in check(change)


@pytest.mark.ts05
def test_ts05_specification_must_be_an_object():
    assert error_codes(checks.check_spec([])) == {"SPC-001"}


@pytest.mark.ts06
@pytest.mark.parametrize("change", [
    lambda s: s["coverage_gaps"].clear(),
    lambda s: s["coverage_gaps"][0].update(reason=""),
    lambda s: s["coverage_gaps"].append({"scenario_id": "S01", "reason": "claimed gap"}),
    lambda s: s["coverage_gaps"].append({"scenario_id": "S99", "reason": "unknown"}),
], ids=["gap-not-declared", "gap-no-reason", "gap-on-covered", "gap-unknown-scenario"])
def test_ts06_coverage_gaps_must_be_explicit_and_consistent(change):
    assert "SPC-003" in check(change)


@pytest.mark.ts06
def test_ts06_scenario_ids_are_unique():
    def change(s):
        s["scenarios"][1]["id"] = "S01"
    assert "SPC-012" in check(change)


@pytest.mark.ts07
def test_ts07_plan_must_fit_the_volume_limit():
    def change(s):
        s["sampling_strategy"]["per_table_allocation"]["CUSTOMER_ORDER"] = 500
    assert "SPC-006" in check(change)


@pytest.mark.ts07
def test_ts07_strategy_cannot_raise_the_limit_of_the_request():
    def change(s):
        s["sampling_strategy"]["max_sample_rows"] = 5000
    assert "SPC-006" in check(change)


@pytest.mark.ts07
def test_ts07_related_tables_need_declared_relationships():
    def change(s):
        s["sampling_strategy"]["relationships"] = []
    assert "SPC-007" in check(change)


@pytest.mark.ts07
def test_ts07_scenarios_must_trace_back_to_rules_of_the_brief():
    def change(s):
        s["scenarios"][0]["rule_refs"] = ["R99"]
    assert "SPC-009" in check(change)


@pytest.mark.ts07
def test_ts07_covered_scenario_needs_a_match_predicate():
    def change(s):
        s["scenarios"][0].pop("match")
    assert "SPC-010" in check(change)


@pytest.mark.ts08
@pytest.mark.parametrize("query", [
    "DELETE FROM CUSTOMER",
    "UPDATE CUSTOMER SET STATUS = 'A'",
    "SELECT 1; DROP TABLE CUSTOMER",
    "INSERT INTO T SELECT * FROM CUSTOMER",
    "CALL purge_customers()",
    "SELECT * FROM CUSTOMER FOR UPDATE",
], ids=["delete", "update", "two-statements", "insert", "call", "for-update"])
def test_ts08_agent_drafts_read_only_queries_only(query):
    def change(s):
        s["scenarios"][0]["extraction_query"] = query
    assert "SPC-008" in check(change)


@pytest.mark.ts08
def test_ts08_cte_select_is_accepted():
    def change(s):
        s["scenarios"][0]["extraction_query"] = "WITH x AS (SELECT 1 AS A) SELECT * FROM x;"
    assert check(change) == set()


@pytest.mark.ts09
@pytest.mark.parametrize("change", [
    lambda s: s["approval"]["approved_by"].update(data_architect="Claude"),
    lambda s: s["approval"]["approved_by"].update(data_owner=""),
    lambda s: s["approval"].update(masking_confirmed=False),
    lambda s: s["approval"].update(gaps_accepted=False),
    lambda s: s["approval"].pop("date"),
    lambda s: s["approval"].update(status="maybe"),
], ids=["agent-approves", "no-owner", "no-masking", "gaps-not-accepted", "no-date", "bad-status"])
def test_ts09_approval_needs_named_humans_and_confirmations(change):
    assert "SPC-011" in check(change)


@pytest.mark.ts09
@pytest.mark.parametrize("status", ["draft", "rejected"])
def test_ts09_extraction_waits_for_approval(status):
    def change(s):
        s["approval"] = {"status": status}
    assert check(change) == set()
    assert "SPC-013" in check(change, require_approved=True)
