"""Shared helpers for the test scenarios."""
import contextlib
import copy
import io
import json
import shutil
from pathlib import Path

from sampling_validator import cli

FIXTURES = Path(__file__).parent / "fixtures"
GOOD = FIXTURES / "good_run"


def load(name):
    return json.loads((GOOD / name).read_text(encoding="utf-8"))


def request():
    return load("request_pack.json")


def brief():
    return load("sampling_brief.json")


def spec():
    return load("sampling_spec.json")


def report():
    return load("coverage_report.json")


def mutated(loader, change):
    """Return a copy of a good artifact after applying one change."""
    obj = copy.deepcopy(loader())
    change(obj)
    return obj


def error_codes(findings):
    return {f.code for f in findings if f.severity == "error"}


def copy_run(tmp_path):
    dst = Path(tmp_path) / "run"
    shutil.copytree(GOOD, dst)
    return dst


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2), encoding="utf-8")


def run_cli(*argv):
    """Run the CLI in-process; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()
