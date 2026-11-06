"""Evaluation protocol: general-purpose LLM vs specialist agent.

See docs/EVALUATION_PROTOCOL.md. Every number is computed here from run results entered by the
scorer; nothing is estimated by a model.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from . import data_guard
from .checks import blank, positive_int
from .findings import Finding, err, warn

ARMS = ("general_llm", "agent", "baseline")
RISK_WEIGHTS = {"high": 3, "medium": 2, "low": 1}
RUN_FIELDS = (
    "run_id", "case_id", "arm", "covered_reference_ids", "proposed_scenarios", "declared_gap_ids",
    "validators_pass", "time_to_approval_min", "iterations", "sample_size_rows", "reviewer_minutes",
)
THRESHOLD_FIELDS = ("min_coverage_gain", "max_critical_misses", "max_effort_ratio")
METRICS = (
    "weighted_coverage", "critical_misses", "precision", "gap_honesty", "validators_pass",
    "time_to_approval_min", "iterations", "sample_size_rows", "reviewer_minutes",
    "effort_minutes", "coverage_per_hour",
)


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ------------------------------------------------------------------ input checks
def check_reference(ref) -> list[Finding]:
    """The reference scenario list written by the Data Architect before any run."""
    if not isinstance(ref, dict):
        return [err("EVL-001", "reference must be a JSON object", "reference")]
    out = [err("EVL-001", f"missing or empty field '{k}'", "reference")
           for k in ("case_id", "scenarios") if blank(ref.get(k))]
    seen = set()
    for idx, scen in enumerate(ref.get("scenarios") or []):
        scen = scen if isinstance(scen, dict) else {}
        where = f"scenarios[{idx}]"
        if blank(scen.get("id")) or blank(scen.get("title")):
            out.append(err("EVL-001", "reference scenario needs an id and a title", where))
        if scen.get("id") in seen:
            out.append(err("EVL-002", f"duplicate reference id '{scen.get('id')}'", where))
        seen.add(scen.get("id"))
        if scen.get("risk") not in RISK_WEIGHTS:
            out.append(err("EVL-002", f"risk must be one of {sorted(RISK_WEIGHTS)}", where))
    return out


def _id_list(run: dict, key: str, ref_ids: set, where: str) -> list[Finding]:
    value = run.get(key)
    if not isinstance(value, list):
        return [err("EVL-006", f"'{key}' must be a list", where)] if key in run else []
    return [err("EVL-005", f"'{ref}' is not a reference scenario of this case", where)
            for ref in value if ref not in ref_ids]


def check_run(run, ref_ids: set, case_id: str) -> list[Finding]:
    """One run result: one engineer, one arm, one case."""
    if not isinstance(run, dict):
        return [err("EVL-003", "run result must be a JSON object", "run")]
    where = f"run {run.get('run_id', '?')}"
    out = [err("EVL-003", f"missing field '{k}'", where) for k in RUN_FIELDS if k not in run]
    if "arm" in run and run["arm"] not in ARMS:
        out.append(err("EVL-004", f"arm must be one of {list(ARMS)}", where))
    if "case_id" in run and run["case_id"] != case_id:
        out.append(err("EVL-007", f"run belongs to case '{run['case_id']}', not '{case_id}'",
                       where))
    out += _id_list(run, "covered_reference_ids", ref_ids, where)
    out += _id_list(run, "declared_gap_ids", ref_ids, where)
    proposed = run.get("proposed_scenarios")
    if "proposed_scenarios" in run and (not isinstance(proposed, list) or not proposed):
        out.append(err("EVL-010", "a run must list the scenarios the arm proposed", where))
    for item in proposed if isinstance(proposed, list) else []:
        item = item if isinstance(item, dict) else {}
        if blank(item.get("title")):
            out.append(err("EVL-003", "proposed scenario needs a title", where))
        if item.get("reference_id") is not None and item["reference_id"] not in ref_ids:
            out.append(err("EVL-005", f"'{item['reference_id']}' is not a reference scenario",
                           where))
    for key in ("time_to_approval_min", "reviewer_minutes"):
        if key in run and not (_number(run[key]) and run[key] >= 0):
            out.append(err("EVL-006", f"'{key}' must be a number of minutes, zero or more",
                           where))
    if "iterations" in run and not positive_int(run["iterations"]):
        out.append(err("EVL-006", "'iterations' must be a positive integer", where))
    size = run.get("sample_size_rows")
    if "sample_size_rows" in run and not (isinstance(size, int) and not isinstance(size, bool)
                                          and size >= 0):
        out.append(err("EVL-006", "'sample_size_rows' must be an integer, zero or more", where))
    if "validators_pass" in run and not isinstance(run["validators_pass"], bool):
        out.append(err("EVL-006", "'validators_pass' must be true or false", where))
    return out


def thresholds_agreed(th) -> bool:
    return (isinstance(th, dict) and not blank(th.get("agreed_by"))
            and not blank(th.get("agreed_on")))


def check_thresholds(th) -> list[Finding]:
    if not isinstance(th, dict):
        return [err("EVL-009", "thresholds must be a JSON object", "thresholds")]
    out = []
    if not thresholds_agreed(th):
        out.append(warn("EVL-009", "thresholds are not agreed: set agreed_by and agreed_on before "
                        "the first run, otherwise no verdict is given", "thresholds"))
    for key in THRESHOLD_FIELDS:
        if not _number(th.get(key)):
            out.append(err("EVL-009", f"threshold '{key}' must be a number", "thresholds"))
    return out


# ------------------------------------------------------------------ scoring
def score_run(run: dict, ref: dict) -> dict:
    """Metrics of one run against the reference list."""
    weight = {s["id"]: RISK_WEIGHTS[s["risk"]] for s in ref["scenarios"]}
    covered = set(run["covered_reference_ids"])
    uncovered = set(weight) - covered
    proposed = run["proposed_scenarios"]
    relevant = sum(1 for p in proposed if p.get("reference_id") is not None)
    effort = run["time_to_approval_min"] + run["reviewer_minutes"]
    coverage = sum(weight[i] for i in covered) / sum(weight.values())
    declared = set(run["declared_gap_ids"]) & uncovered
    return {
        "run_id": run["run_id"],
        "weighted_coverage": coverage,
        "critical_misses": sum(1 for s in ref["scenarios"]
                               if s["risk"] == "high" and s["id"] not in covered),
        "precision": relevant / len(proposed),
        "gap_honesty": len(declared) / len(uncovered) if uncovered else 1.0,
        "validators_pass": 1.0 if run["validators_pass"] else 0.0,
        "time_to_approval_min": run["time_to_approval_min"],
        "iterations": run["iterations"],
        "sample_size_rows": run["sample_size_rows"],
        "reviewer_minutes": run["reviewer_minutes"],
        "effort_minutes": effort,
        "coverage_per_hour": coverage / (effort / 60) if effort > 0 else None,
    }


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def summarise(scored: dict) -> tuple[dict, dict]:
    """scored: {case: {arm: [metrics...]}} -> per case medians, overall median of case medians."""
    per_case = {case: {arm: {m: _median(r[m] for r in runs) for m in METRICS}
                       for arm, runs in arms.items()} for case, arms in scored.items()}
    arms = {arm for case in per_case.values() for arm in case}
    overall = {arm: {m: _median(case[arm][m] for case in per_case.values() if arm in case)
                     for m in METRICS} for arm in arms}
    return per_case, overall


def decide(overall: dict, thresholds, n_cases: int) -> dict:
    """The success rule of the protocol. No verdict unless thresholds were agreed in advance."""
    if not thresholds_agreed(thresholds) or any(not _number(thresholds.get(k))
                                                for k in THRESHOLD_FIELDS):
        return {"status": "NOT_EVALUABLE", "rules": [],
                "reasons": ["thresholds are not agreed and valid: no verdict can be given"]}
    if "agent" not in overall or "general_llm" not in overall:
        return {"status": "NOT_EVALUABLE", "rules": [],
                "reasons": ["both arms, 'agent' and 'general_llm', are needed"]}
    agent, llm = overall["agent"], overall["general_llm"]
    if not llm["effort_minutes"]:
        return {"status": "NOT_EVALUABLE", "rules": [],
                "reasons": ["the general_llm arm has no recorded effort"]}
    ratio = agent["effort_minutes"] / llm["effort_minutes"]
    gain = agent["weighted_coverage"] - llm["weighted_coverage"]
    rules = [
        {"rule": "coverage gain (agent minus general LLM)", "value": gain, "op": ">=",
         "limit": thresholds["min_coverage_gain"], "ok": gain >= thresholds["min_coverage_gain"]},
        {"rule": "critical misses of the agent", "value": agent["critical_misses"], "op": "<=",
         "limit": thresholds["max_critical_misses"],
         "ok": agent["critical_misses"] <= thresholds["max_critical_misses"]},
        {"rule": "effort ratio (agent / general LLM)", "value": ratio, "op": "<=",
         "limit": thresholds["max_effort_ratio"], "ok": ratio <= thresholds["max_effort_ratio"]},
    ]
    reasons = []
    if n_cases < 2:
        reasons.append("fewer than 2 cases: read the result as an indication only")
    return {"status": "PASS" if all(r["ok"] for r in rules) else "FAIL", "rules": rules,
            "reasons": reasons}


# ------------------------------------------------------------------ loading and reporting
def _load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(directory) -> dict:
    """Read thresholds, cases and runs from a folder; return findings, metrics and verdict."""
    root = Path(directory)
    findings: list[Finding] = []
    illustrative = False
    thresholds = None
    if (root / "thresholds.json").is_file():
        thresholds = _load(root / "thresholds.json")
        findings += check_thresholds(thresholds) + data_guard.scan_artifact(thresholds)
        illustrative |= bool(isinstance(thresholds, dict) and thresholds.get("_illustrative"))
    else:
        findings.append(err("EVL-009", "thresholds.json not found", "thresholds"))
    case_dirs = sorted(p for p in (root / "cases").glob("*") if p.is_dir()) \
        if (root / "cases").is_dir() else []
    if not case_dirs:
        findings.append(err("EVL-001", "no case found under cases/", "cases"))
    scored: dict = {}
    n_runs = 0
    for case_dir in case_dirs:
        ref_path = case_dir / "reference_scenarios.json"
        if not ref_path.is_file():
            findings.append(err("EVL-001", "reference_scenarios.json not found", case_dir.name))
            continue
        ref = _load(ref_path)
        ref_findings = check_reference(ref)
        findings += ref_findings + data_guard.scan_artifact(ref, case_dir.name)
        illustrative |= bool(isinstance(ref, dict) and ref.get("_illustrative"))
        if ref_findings:
            continue
        ref_ids = {s["id"] for s in ref["scenarios"]}
        seen_runs = set()
        for run_path in sorted((case_dir / "runs").glob("*.json")):
            run = _load(run_path)
            run_findings = check_run(run, ref_ids, ref["case_id"])
            if isinstance(run, dict) and run.get("run_id") in seen_runs:
                run_findings.append(err("EVL-008", "duplicate run_id", run_path.name))
            findings += run_findings + data_guard.scan_artifact(run, run_path.name)
            if isinstance(run, dict):
                seen_runs.add(run.get("run_id"))
                illustrative |= bool(run.get("_illustrative"))
            if not run_findings:
                scored.setdefault(ref["case_id"], {}).setdefault(run["arm"], []).append(
                    score_run(run, ref))
                n_runs += 1
    per_case, overall = summarise(scored)
    return {"findings": findings, "illustrative": illustrative, "n_runs": n_runs,
            "per_case": per_case, "overall": overall,
            "verdict": decide(overall, thresholds, len(per_case))}


ROWS = (
    ("Weighted coverage", "weighted_coverage", "pct"),
    ("Critical misses", "critical_misses", "num"),
    ("Precision", "precision", "pct"),
    ("Gap honesty", "gap_honesty", "pct"),
    ("Validators pass", "validators_pass", "pct"),
    ("Time to approval (min)", "time_to_approval_min", "num"),
    ("Iterations", "iterations", "num"),
    ("Sample size (rows)", "sample_size_rows", "num"),
    ("Reviewer effort (min)", "reviewer_minutes", "num"),
    ("Total effort (min)", "effort_minutes", "num"),
    ("Coverage per hour of effort", "coverage_per_hour", "num2"),
)


def _fmt(value, kind: str) -> str:
    if value is None:
        return "n/a"
    return {"pct": f"{value:.0%}", "num": f"{value:.1f}", "num2": f"{value:.2f}"}[kind]


def _table(block: dict) -> list[str]:
    arms = sorted(block)
    lines = ["| Metric | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for label, key, kind in ROWS:
        lines.append(f"| {label} | " + " | ".join(_fmt(block[a][key], kind) for a in arms) + " |")
    return lines


def render_report(result: dict) -> str:
    lines = ["# Evaluation report: general-purpose LLM vs specialist agent", ""]
    if result["illustrative"]:
        lines += ["> ILLUSTRATIVE DATA: these are not real results.", ""]
    for finding in result["findings"]:
        lines.append(f"- {finding}")
    if result["findings"]:
        lines.append("")
    verdict = result["verdict"]
    lines += [f"Runs scored: {result['n_runs']}  |  Cases: {len(result['per_case'])}", "",
              f"## Verdict: {verdict['status']}", ""]
    if verdict["rules"]:
        lines += ["| Rule | Value | Limit | Result |", "|---|---|---|---|"]
        for rule in verdict["rules"]:
            lines.append(f"| {rule['rule']} | {rule['value']:.2f} | {rule['op']} {rule['limit']} | "
                         f"{'ok' if rule['ok'] else 'not met'} |")
        lines.append("")
    lines += [f"- {reason}" for reason in verdict["reasons"]]
    lines += ["- With a handful of cases, read medians and spread. This is not a statistical test.",
              ""]
    for case, block in sorted(result["per_case"].items()):
        lines += [f"## Case {case} (median of runs)", ""] + _table(block) + [""]
    if result["overall"]:
        lines += ["## Overall (median of the case medians)", ""] + _table(result["overall"]) + [""]
    return "\n".join(lines)
