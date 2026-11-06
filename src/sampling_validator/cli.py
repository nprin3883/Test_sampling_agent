"""Command line entry point: python -m sampling_validator.cli <command> ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import checks, data_guard, evaluation, verify_sample
from .findings import Finding, err, has_errors

RUN_FILES = {
    "request": "request_pack.json",
    "brief": "sampling_brief.json",
    "spec": "sampling_spec.json",
    "report": "coverage_report.json",
}


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _emit(label: str, findings: list[Finding], as_json: bool) -> None:
    if as_json:
        print(json.dumps({"artifact": label, "findings": [f.as_dict() for f in findings]}))
        return
    status = "FAIL" if has_errors(findings) else "PASS"
    print(f"[{status}] {label}")
    for finding in findings:
        print(f"   {finding}")


def _guard(artifact) -> list[Finding]:
    return data_guard.scan_artifact(artifact)


def _run_report_checks(report, spec, sample_dir) -> list[Finding]:
    if spec is None:
        return [err("COV-004", "a coverage report needs the approved sampling_spec.json next to it",
                    "coverage_report")]
    findings = checks.check_coverage_report(report, spec) + _guard(report)
    if sample_dir:
        sample = verify_sample.load_sample(sample_dir)
        recomputed = verify_sample.build_report(spec, sample, report.get("ticket_ref"))
        findings += checks.compare_reports(report, recomputed) + data_guard.scan_sample(sample)
    return findings


def cmd_request(args) -> int:
    pack = _load(args.file)
    findings = checks.check_request_pack(pack) + _guard(pack)
    _emit("request pack", findings, args.json)
    return int(has_errors(findings))


def cmd_brief(args) -> int:
    brief = _load(args.file)
    request = _load(args.request) if args.request else None
    findings = checks.check_brief(brief, request) + _guard(brief)
    _emit("sampling brief", findings, args.json)
    return int(has_errors(findings))


def cmd_spec(args) -> int:
    spec = _load(args.file)
    brief = _load(args.brief) if args.brief else None
    request = _load(args.request) if args.request else None
    findings = checks.check_spec(spec, brief, request, args.require_approved) + _guard(spec)
    _emit("sampling specification", findings, args.json)
    return int(has_errors(findings))


def cmd_report(args) -> int:
    findings = _run_report_checks(_load(args.file), _load(args.spec), args.sample_dir)
    _emit("coverage report", findings, args.json)
    return int(has_errors(findings))


def cmd_verify(args) -> int:
    spec = _load(args.spec)
    sample = verify_sample.load_sample(args.sample_dir)
    report = verify_sample.build_report(spec, sample, args.ticket)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    elif not args.json:
        print(text)
    findings = checks.check_coverage_report(report, spec) + data_guard.scan_sample(sample)
    _emit("coverage report (computed from the sample)", findings, args.json)
    return int(has_errors(findings))


def cmd_check_run(args) -> int:
    run = Path(args.dir)
    docs = {k: _load(run / name) for k, name in RUN_FILES.items() if (run / name).exists()}
    if not docs:
        print(f"[FAIL] no artifacts found in {run}")
        return 1
    failed = False
    plan = [
        ("request", lambda: checks.check_request_pack(docs["request"])),
        ("brief", lambda: checks.check_brief(docs["brief"], docs.get("request"))),
        ("spec", lambda: checks.check_spec(docs["spec"], docs.get("brief"), docs.get("request"),
                                           require_approved="report" in docs)),
        ("report", lambda: _run_report_checks(
            docs["report"], docs.get("spec"),
            run / "sample" if (run / "sample").is_dir() else None)),
    ]
    for key, step in plan:
        if key not in docs:
            print(f"[SKIP] {RUN_FILES[key]} not present yet")
            continue
        findings = step() + (_guard(docs[key]) if key != "report" else [])
        _emit(RUN_FILES[key], findings, args.json)
        failed |= has_errors(findings)
    print("RESULT:", "FAIL" if failed else "PASS")
    return int(failed)


def cmd_evaluate(args) -> int:
    result = evaluation.evaluate(args.dir)
    report = evaluation.render_report(result)
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps({**result, "findings": [f.as_dict() for f in result["findings"]]}))
    else:
        print(report)
    return int(has_errors(result["findings"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sampling_validator")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("request", help="check the step 1 request pack")
    p.add_argument("file")
    p.set_defaults(func=cmd_request)

    p = sub.add_parser("brief", help="check the step 2 sampling brief")
    p.add_argument("file")
    p.add_argument("--request")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("spec", help="check the step 3/4 sampling specification")
    p.add_argument("file")
    p.add_argument("--brief")
    p.add_argument("--request")
    p.add_argument("--require-approved", action="store_true")
    p.set_defaults(func=cmd_spec)

    p = sub.add_parser("report", help="check a step 5 coverage report")
    p.add_argument("file")
    p.add_argument("--spec", required=True)
    p.add_argument("--sample-dir")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("verify", help="compute the coverage report from an extracted sample")
    p.add_argument("--spec", required=True)
    p.add_argument("--sample-dir", required=True)
    p.add_argument("--ticket", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("evaluate", help="score the agent against a general-purpose LLM")
    p.add_argument("dir")
    p.add_argument("--out", help="also write the report as Markdown")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("check-run", help="check every artifact present in a run folder")
    p.add_argument("dir")
    p.set_defaults(func=cmd_check_run)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
