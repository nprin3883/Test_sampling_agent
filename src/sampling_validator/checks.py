"""Checks on the artifacts the sampling agent produces (card steps 1 to 5).

Artifacts are JSON files: request pack (step 1), sampling brief (step 2),
sampling specification (steps 3 and 4) and coverage report (step 5).
"""
from __future__ import annotations

import re

from .findings import Finding, err, warn

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
EDGE_CATEGORIES = ("null", "boundary", "duplicate", "tie", "late_arriving", "corrected", "deleted")
SCENARIO_CATEGORIES = EDGE_CATEGORIES + ("business",)
APPROVAL_STATUSES = ("draft", "approved", "rejected")

REQUEST_FIELDS = (
    "migration_id", "ticket_ref", "specification_ref", "acceptance_criteria",
    "source_definitions", "target_definitions", "environments", "constraints",
)
BRIEF_FIELDS = ("status", "code_available", "confidence", "inputs_used", "business_rules")
SPEC_FIELDS = ("scenarios", "sampling_strategy", "approval")
STRATEGY_FIELDS = ("max_sample_rows", "per_table_allocation")
REPORT_FIELDS = (
    "ticket_ref", "spec_status", "total_rows", "rows_by_table", "scenario_coverage",
    "referential_integrity", "volume_limit", "summary",
)

WRITE_SQL = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|truncate|create|grant|revoke|call|exec|execute)\b",
    re.I,
)
SELF_APPROVER = re.compile(r"\b(ai|agent|claude|copilot|cursor|bot|assistant|llm)\b", re.I)


def blank(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def missing_fields(obj, keys, where: str, code: str) -> list[Finding]:
    if not isinstance(obj, dict):
        return [err(code, "must be a JSON object", where)]
    return [err(code, f"missing or empty field '{k}'", where) for k in keys if blank(obj.get(k))]


def positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- step 1
def check_request_pack(pack) -> list[Finding]:
    out = missing_fields(pack, REQUEST_FIELDS, "request_pack", "REQ-001")
    if not isinstance(pack, dict):
        return out
    if "source_code_refs" not in pack:
        out.append(err("REQ-001", "missing field 'source_code_refs' (use [] if none)",
                       "request_pack"))
    elif not pack["source_code_refs"]:
        out.append(warn("REQ-005", "no source code provided: scenarios come from the data "
                        "profile only and the brief must state reduced confidence", "request_pack"))
    constraints = _as_dict(pack.get("constraints"))
    if not positive_int(constraints.get("max_sample_rows")):
        out.append(err("REQ-002", "constraints.max_sample_rows must be a positive integer",
                       "constraints"))
    if blank(constraints.get("data_handling_rules")):
        out.append(err("REQ-003", "constraints.data_handling_rules must list at least one rule",
                       "constraints"))
    for idx, table in enumerate(pack.get("source_definitions") or []):
        for key in ("table", "attributes", "keys"):
            if blank(_as_dict(table).get(key)):
                out.append(err("REQ-004", f"source definition lacks '{key}'",
                               f"source_definitions[{idx}]"))
    return out


# ---------------------------------------------------------------- step 2
def check_brief(brief, request=None) -> list[Finding]:
    out = missing_fields(brief, BRIEF_FIELDS, "sampling_brief", "BRF-005")
    if not isinstance(brief, dict):
        return out
    if _as_dict(brief.get("inputs_used")).get("raw_records"):
        out.append(err("BRF-001", "the agent must work on schemas, profiling statistics and code, "
                       "never on raw records", "inputs_used.raw_records"))
    open_blocking = [q.get("id", "?") for q in brief.get("open_questions") or []
                     if _as_dict(q).get("blocking") and not _as_dict(q).get("answered")]
    if brief.get("status") == "validated" and open_blocking:
        out.append(err("BRF-002", "brief is 'validated' but blocking questions are unanswered: "
                       + ", ".join(open_blocking), "open_questions"))
    for idx, rule in enumerate(brief.get("business_rules") or []):
        if blank(_as_dict(rule).get("source_ref")) or blank(_as_dict(rule).get("id")):
            out.append(err("BRF-003", "business rule needs an id and a source_ref (code location "
                           "or specification section)", f"business_rules[{idx}]"))
    if brief.get("code_available") is False and brief.get("confidence") != "reduced":
        out.append(err("BRF-004", "without source code the brief must declare confidence 'reduced'",
                       "confidence"))
    if request is not None and brief.get("code_available") and not _as_dict(request).get(
            "source_code_refs"):
        out.append(err("BRF-006", "brief claims source code was read but the request pack "
                       "provides none", "code_available"))
    return out


# ------------------------------------------------------------- steps 3, 4
def check_spec(spec, brief=None, request=None, require_approved: bool = False) -> list[Finding]:
    out = missing_fields(spec, SPEC_FIELDS, "sampling_spec", "SPC-001")
    if not isinstance(spec, dict):
        return out
    rule_ids = None
    if isinstance(brief, dict):
        rule_ids = {r.get("id") for r in brief.get("business_rules") or [] if isinstance(r, dict)}
    out += _check_scenarios(spec, rule_ids)
    out += _check_gaps(spec)
    out += _check_categories(spec)
    out += _check_strategy(spec, request)
    out += _check_approval(spec, require_approved)
    return out


def _check_scenarios(spec: dict, rule_ids) -> list[Finding]:
    out, seen = [], set()
    ranks = []
    for idx, scen in enumerate(spec.get("scenarios") or []):
        scen = _as_dict(scen)
        where = f"scenarios[{idx}]"
        sid = scen.get("id")
        if sid in seen:
            out.append(err("SPC-012", f"duplicate scenario id '{sid}'", where))
        seen.add(sid)
        for key in ("id", "title", "rationale", "category", "risk"):
            if blank(scen.get(key)):
                out.append(err("SPC-002", f"scenario lacks '{key}'", where))
        if scen.get("category") not in SCENARIO_CATEGORIES:
            out.append(err("SPC-002", f"unknown category '{scen.get('category')}'", where))
        if scen.get("risk") not in RISK_ORDER:
            out.append(err("SPC-002", f"risk must be one of {sorted(RISK_ORDER)}", where))
        else:
            ranks.append(RISK_ORDER[scen["risk"]])
        if not isinstance(scen.get("covered"), bool):
            out.append(err("SPC-002", "'covered' must be true or false", where))
        if scen.get("covered") is True:
            if blank(scen.get("extraction_query")) or blank(scen.get("match")):
                out.append(err("SPC-010", "a covered scenario needs an extraction_query and a "
                               "match predicate so the sample can be verified", where))
            else:
                out += _check_query(scen["extraction_query"], where)
        if rule_ids is not None:
            for ref in scen.get("rule_refs") or []:
                if ref not in rule_ids:
                    out.append(err("SPC-009", f"rule '{ref}' is not in the sampling brief", where))
    if ranks != sorted(ranks):
        out.append(err("SPC-004", "scenarios must be ranked by business risk, high first",
                       "scenarios"))
    return out


def _check_query(query: str, where: str) -> list[Finding]:
    text = query.strip().rstrip(";").strip()
    if not re.match(r"(?i)^(select|with)\b", text) or WRITE_SQL.search(text) or ";" in text:
        return [err("SPC-008", "extraction queries must be a single read-only SELECT: the agent "
                    "drafts, the engineer runs", where)]
    return []


def _check_gaps(spec: dict) -> list[Finding]:
    out = []
    scenarios = {s.get("id"): s for s in spec.get("scenarios") or [] if isinstance(s, dict)}
    gap_ids = set()
    for idx, gap in enumerate(spec.get("coverage_gaps") or []):
        gap = _as_dict(gap)
        where = f"coverage_gaps[{idx}]"
        gap_ids.add(gap.get("scenario_id"))
        if gap.get("scenario_id") not in scenarios:
            out.append(err("SPC-003", "gap refers to an unknown scenario", where))
        elif scenarios[gap["scenario_id"]].get("covered") is True:
            out.append(err("SPC-003", "gap declared for a scenario marked as covered", where))
        if blank(gap.get("reason")):
            out.append(err("SPC-003", "a coverage gap must say why it cannot be covered", where))
    for sid, scen in scenarios.items():
        if scen.get("covered") is False and sid not in gap_ids:
            out.append(err("SPC-003", f"scenario '{sid}' is not covered and not declared as a gap",
                           "coverage_gaps"))
    return out


def _check_categories(spec: dict) -> list[Finding]:
    not_applicable = _as_dict(spec.get("edge_categories_not_applicable"))
    present = {s.get("category") for s in spec.get("scenarios") or [] if isinstance(s, dict)}
    present |= {k for k, reason in not_applicable.items() if not blank(reason)}
    return [err("SPC-005", f"edge category '{cat}' is neither a scenario nor declared "
                "not applicable with a reason", "edge_categories_not_applicable")
            for cat in EDGE_CATEGORIES if cat not in present]


def _check_strategy(spec: dict, request) -> list[Finding]:
    strategy = _as_dict(spec.get("sampling_strategy"))
    out = missing_fields(strategy, STRATEGY_FIELDS, "sampling_strategy", "SPC-001")
    allocation = _as_dict(strategy.get("per_table_allocation"))
    limit = strategy.get("max_sample_rows")
    if request is not None:
        limit = _as_dict(_as_dict(request).get("constraints")).get("max_sample_rows", limit)
        if positive_int(strategy.get("max_sample_rows")) and positive_int(limit) \
                and strategy["max_sample_rows"] > limit:
            out.append(err("SPC-006", "strategy limit is above the limit in the request pack",
                           "sampling_strategy"))
    planned = sum(v for v in allocation.values() if isinstance(v, int))
    if positive_int(limit) and planned > limit:
        out.append(err("SPC-006", f"planned {planned} rows exceed the limit of {limit}",
                       "sampling_strategy.per_table_allocation"))
    if len(allocation) > 1 and blank(strategy.get("relationships")):
        out.append(err("SPC-007", "several tables are sampled: declare the relationships that keep "
                       "related records consistent", "sampling_strategy.relationships"))
    return out


def _check_approval(spec: dict, require_approved: bool) -> list[Finding]:
    approval = _as_dict(spec.get("approval"))
    status = approval.get("status")
    if status not in APPROVAL_STATUSES:
        return [err("SPC-011", f"approval.status must be one of {list(APPROVAL_STATUSES)}",
                    "approval")]
    out = []
    if status == "approved":
        by = _as_dict(approval.get("approved_by"))
        for role in ("data_architect", "data_owner"):
            name = by.get(role)
            if blank(name) or SELF_APPROVER.search(str(name)):
                out.append(err("SPC-011", f"approval needs a named human {role}; the agent cannot "
                               "approve its own specification", "approval.approved_by"))
        if approval.get("masking_confirmed") is not True:
            out.append(err("SPC-011", "masking and data-handling requirements are not confirmed",
                           "approval.masking_confirmed"))
        if approval.get("gaps_accepted") is not True:
            out.append(err("SPC-011", "coverage gaps are not accepted", "approval.gaps_accepted"))
        if blank(approval.get("date")):
            out.append(err("SPC-011", "approval date is missing", "approval.date"))
    elif require_approved:
        out.append(err("SPC-013", f"specification is '{status}': extraction must wait for human "
                       "approval", "approval.status"))
    return out


# ---------------------------------------------------------------- step 5
def check_coverage_report(report, spec) -> list[Finding]:
    out = missing_fields(report, REPORT_FIELDS, "coverage_report", "COV-007")
    if not isinstance(report, dict):
        return out
    if "ticket_ref" in report and blank(report["ticket_ref"]):
        out.append(err("COV-005", "the report must link to the migration ticket", "ticket_ref"))
    if _as_dict(_as_dict(spec).get("approval")).get("status") != "approved":
        out.append(err("COV-004", "report built against a specification that is not approved",
                       "spec.approval"))
    limit = _as_dict(_as_dict(spec).get("sampling_strategy")).get("max_sample_rows")
    if positive_int(limit) and isinstance(report.get("total_rows"), int) \
            and report["total_rows"] > limit:
        out.append(err("COV-001", f"sample has {report['total_rows']} rows, limit is {limit}",
                       "total_rows"))
    out += _check_scenario_coverage(report, spec)
    for idx, chk in enumerate(_as_dict(report.get("referential_integrity")).get("checks") or []):
        if _as_dict(chk).get("orphans", 0) > 0:
            out.append(err("COV-003", f"{chk['orphans']} orphan rows in {chk.get('child')} "
                           f"without a parent in {chk.get('parent')}",
                           f"referential_integrity.checks[{idx}]"))
    return out


def _check_scenario_coverage(report: dict, spec) -> list[Finding]:
    out = []
    expected = {s["id"]: s for s in _as_dict(spec).get("scenarios") or []
                if isinstance(s, dict) and "id" in s}
    reported = {c.get("scenario_id"): c for c in report.get("scenario_coverage") or []
                if isinstance(c, dict)}
    if set(expected) != set(reported):
        out.append(err("COV-006", "report and specification list different scenarios: "
                       f"{sorted(set(expected) ^ set(reported), key=str)}", "scenario_coverage"))
    missed = []
    for sid, scen in expected.items():
        matched = _as_dict(reported.get(sid)).get("matched_rows", 0)
        if scen.get("covered") is True and matched < 1:
            missed.append(sid)
            out.append(err("COV-002", f"scenario '{sid}' is promised by the specification but "
                           "absent from the sample", "scenario_coverage"))
    summary = _as_dict(report.get("summary"))
    if summary and sorted(summary.get("missed", [])) != sorted(missed):
        out.append(err("COV-009", "summary.missed does not match the scenario coverage",
                       "summary"))
    return out


def compare_reports(reported, recomputed) -> list[Finding]:
    """The numbers in a report must be reproducible from the extracted sample."""
    out = []
    if reported.get("rows_by_table") != recomputed.get("rows_by_table"):
        out.append(err("COV-008", "rows_by_table cannot be reproduced from the sample",
                       "rows_by_table"))
    mine = {c.get("scenario_id"): c.get("matched_rows")
            for c in reported.get("scenario_coverage", [])}
    theirs = {c["scenario_id"]: c["matched_rows"] for c in recomputed["scenario_coverage"]}
    for sid in sorted(set(mine) | set(theirs), key=str):
        if mine.get(sid) != theirs.get(sid):
            out.append(err("COV-008", f"scenario '{sid}': report says {mine.get(sid)} matching "
                           f"rows, the sample gives {theirs.get(sid)}", "scenario_coverage"))
    return out
