"""Step 5: compare an extracted sample with the approved specification.

The coverage numbers are computed here, never estimated by the agent.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def load_sample(sample_dir) -> dict[str, list[dict]]:
    """Read one CSV per table: <TABLE>.csv."""
    sample = {}
    for path in sorted(Path(sample_dir).glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            sample[path.stem] = list(csv.DictReader(handle))
    return sample


def _null(value) -> bool:
    return value is None or str(value).strip() == ""


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _holds(row: dict, cond: dict, counts: Counter) -> bool:
    value, op, ref = row.get(cond["field"]), cond["op"], cond.get("value")
    if op == "is_null":
        return _null(value)
    if op == "not_null":
        return not _null(value)
    if op == "duplicate":
        return not _null(value) and counts[value] > 1
    if _null(value):
        return False
    if op == "eq":
        return str(value) == str(ref)
    if op == "ne":
        return str(value) != str(ref)
    if op == "in":
        return str(value) in [str(x) for x in ref]
    if op == "between":
        try:
            return _num(ref[0]) <= _num(value) <= _num(ref[1])
        except TypeError:
            return False
    compare = {"lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
               "gt": lambda a, b: a > b, "gte": lambda a, b: a >= b}
    if op in compare:
        try:
            return compare[op](_num(value), _num(ref))
        except TypeError:  # text compared with a number never matches
            return False
    raise ValueError(f"unknown operator '{op}'")


def count_matches(sample: dict[str, list[dict]], match: dict) -> int:
    """Rows of match['table'] that satisfy every condition."""
    rows = sample.get(match["table"], [])
    total = 0
    for cond in match["conditions"]:
        if cond["op"] == "duplicate":
            counts = Counter(r.get(cond["field"]) for r in rows if not _null(r.get(cond["field"])))
            break
    else:
        counts = Counter()
    for row in rows:
        if all(_holds(row, cond, counts) for cond in match["conditions"]):
            total += 1
    return total


def _orphans(sample: dict, rel: dict) -> int:
    parent_key = rel.get("parent_key", rel["key"])
    child_key = rel.get("child_key", rel["key"])
    parents = {r.get(parent_key) for r in sample.get(rel["parent"], [])}
    return sum(1 for r in sample.get(rel["child"], []) if r.get(child_key) not in parents)


def build_report(spec: dict, sample: dict[str, list[dict]], ticket_ref: str) -> dict:
    strategy = spec["sampling_strategy"]
    rows_by_table = {table: len(rows) for table, rows in sample.items()}
    total = sum(rows_by_table.values())
    coverage = []
    for scen in spec["scenarios"]:
        matched = count_matches(sample, scen["match"]) if scen.get("match") else 0
        coverage.append({"scenario_id": scen["id"], "matched_rows": matched})
    by_id = {c["scenario_id"]: c["matched_rows"] for c in coverage}
    covered_ok = [s["id"] for s in spec["scenarios"] if s["covered"] and by_id[s["id"]] >= 1]
    missed = [s["id"] for s in spec["scenarios"] if s["covered"] and by_id[s["id"]] < 1]
    gaps = [s["id"] for s in spec["scenarios"] if not s["covered"]]
    checks = [{"parent": r["parent"], "child": r["child"], "key": r["key"],
               "orphans": _orphans(sample, r)} for r in strategy.get("relationships", [])]
    return {
        "ticket_ref": ticket_ref,
        "spec_status": spec.get("approval", {}).get("status"),
        "total_rows": total,
        "rows_by_table": rows_by_table,
        "scenario_coverage": coverage,
        "referential_integrity": {"checks": checks,
                                  "ok": all(c["orphans"] == 0 for c in checks)},
        "volume_limit": {"max_sample_rows": strategy["max_sample_rows"], "total_rows": total,
                         "ok": total <= strategy["max_sample_rows"]},
        "summary": {"covered": covered_ok, "missed": missed, "declared_gaps": gaps},
    }
