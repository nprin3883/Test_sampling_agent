"""Scenarios TS-01 to TS-04: the request pack (step 1) and the sampling brief (step 2)."""
import pytest

from helpers import brief, error_codes, mutated, request
from sampling_validator import checks


@pytest.mark.ts01
def test_ts01_complete_request_pack_is_accepted():
    assert error_codes(checks.check_request_pack(request())) == set()


@pytest.mark.ts01
@pytest.mark.parametrize("change, expected", [
    (lambda p: p.pop("constraints"), "REQ-001"),
    (lambda p: p.pop("source_code_refs"), "REQ-001"),
    (lambda p: p["constraints"].update(max_sample_rows=0), "REQ-002"),
    (lambda p: p["constraints"].update(max_sample_rows=True), "REQ-002"),
    (lambda p: p["constraints"].update(data_handling_rules=[]), "REQ-003"),
    (lambda p: p["source_definitions"][0].pop("keys"), "REQ-004"),
], ids=["no-constraints", "no-code-key", "limit-zero", "limit-bool", "no-rules", "table-no-keys"])
def test_ts01_incomplete_request_pack_is_rejected(change, expected):
    findings = checks.check_request_pack(mutated(request, change))
    assert expected in error_codes(findings)


@pytest.mark.ts01
def test_ts01_missing_code_is_a_warning_not_an_error():
    findings = checks.check_request_pack(mutated(request, lambda p: p.update(source_code_refs=[])))
    assert error_codes(findings) == set()
    assert [f.code for f in findings if f.severity == "warning"] == ["REQ-005"]


@pytest.mark.ts01
def test_ts01_request_pack_must_be_an_object():
    assert error_codes(checks.check_request_pack(["not", "an", "object"])) == {"REQ-001"}


@pytest.mark.ts02
def test_ts02_good_brief_works_on_metadata_only():
    assert error_codes(checks.check_brief(brief(), request())) == set()


@pytest.mark.ts02
def test_ts02_brief_built_on_raw_records_is_rejected():
    bad = mutated(brief, lambda b: b["inputs_used"].update(raw_records=True))
    assert "BRF-001" in error_codes(checks.check_brief(bad))


@pytest.mark.ts02
def test_ts02_brief_must_be_an_object():
    assert error_codes(checks.check_brief("text")) == {"BRF-005"}


@pytest.mark.ts03
def test_ts03_validated_brief_cannot_hide_blocking_questions():
    def change(b):
        b["open_questions"][0]["answered"] = False
    assert "BRF-002" in error_codes(checks.check_brief(mutated(brief, change)))


@pytest.mark.ts03
def test_ts03_unanswered_questions_are_fine_while_the_brief_is_still_open():
    def change(b):
        b["open_questions"][0]["answered"] = False
        b["status"] = "needs_answers"
    assert error_codes(checks.check_brief(mutated(brief, change))) == set()


@pytest.mark.ts03
def test_ts03_every_business_rule_needs_evidence():
    bad = mutated(brief, lambda b: b["business_rules"][0].pop("source_ref"))
    assert "BRF-003" in error_codes(checks.check_brief(bad))


@pytest.mark.ts04
def test_ts04_missing_code_requires_reduced_confidence():
    def change(b):
        b["code_available"] = False
    assert "BRF-004" in error_codes(checks.check_brief(mutated(brief, change)))


@pytest.mark.ts04
def test_ts04_missing_code_with_reduced_confidence_is_accepted():
    def change(b):
        b.update(code_available=False, confidence="reduced")
    assert error_codes(checks.check_brief(mutated(brief, change))) == set()


@pytest.mark.ts04
def test_ts04_brief_cannot_claim_code_the_request_never_provided():
    req = mutated(request, lambda p: p.update(source_code_refs=[]))
    assert "BRF-006" in error_codes(checks.check_brief(brief(), req))
