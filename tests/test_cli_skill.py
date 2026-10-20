"""Scenarios TS-13 and TS-14: the command line, end to end, and the packaged skill."""
import csv
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from helpers import GOOD, copy_run, load, run_cli, write_json

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "src"))


def edit(run, name, change):
    doc = json.loads((run / name).read_text(encoding="utf-8"))
    change(doc)
    write_json(run / name, doc)


@pytest.mark.ts13
def test_ts13_complete_run_passes():
    code, out, _ = run_cli("check-run", GOOD)
    assert code == 0
    assert "RESULT: PASS" in out


@pytest.mark.ts13
def test_ts13_partial_run_skips_what_does_not_exist_yet(tmp_path):
    run = Path(tmp_path) / "run"
    run.mkdir()
    (run / "request_pack.json").write_text((GOOD / "request_pack.json").read_text(), "utf-8")
    code, out, _ = run_cli("check-run", run)
    assert code == 0
    assert out.count("[SKIP]") == 3


@pytest.mark.ts13
def test_ts13_empty_folder_fails(tmp_path):
    code, out, _ = run_cli("check-run", tmp_path)
    assert code == 1
    assert "no artifacts" in out


@pytest.mark.ts13
def test_ts13_broken_specification_fails_the_run(tmp_path):
    run = copy_run(tmp_path)
    edit(run, "sampling_spec.json",
         lambda s: s["scenarios"][0].update(extraction_query="DELETE FROM X"))
    code, out, _ = run_cli("check-run", run)
    assert code == 1
    assert "SPC-008" in out


@pytest.mark.ts13
def test_ts13_report_on_an_unapproved_specification_fails(tmp_path):
    run = copy_run(tmp_path)
    edit(run, "sampling_spec.json", lambda s: s.update(approval={"status": "draft"}))
    code, out, _ = run_cli("check-run", run)
    assert code == 1
    assert "SPC-013" in out and "COV-004" in out


@pytest.mark.ts13
def test_ts13_report_without_a_specification_fails(tmp_path):
    run = copy_run(tmp_path)
    (run / "sampling_spec.json").unlink()
    code, out, _ = run_cli("check-run", run)
    assert code == 1
    assert "COV-004" in out


@pytest.mark.ts13
def test_ts13_report_that_disagrees_with_the_sample_fails(tmp_path):
    run = copy_run(tmp_path)
    edit(run, "coverage_report.json",
         lambda r: r["scenario_coverage"][0].update(matched_rows=99))
    code, out, _ = run_cli("check-run", run)
    assert code == 1
    assert "COV-008" in out


@pytest.mark.ts13
def test_ts13_unmasked_sample_fails_the_run(tmp_path):
    run = copy_run(tmp_path)
    path = run / "sample" / "CUSTOMER.csv"
    rows = list(csv.reader(path.open(encoding="utf-8")))
    rows[1][1] = "jane.doe@client-corp.com"
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    code, out, _ = run_cli("check-run", run)
    assert code == 1
    assert "DAT-002" in out


@pytest.mark.ts13
def test_ts13_each_command_accepts_the_good_run(tmp_path):
    out_file = Path(tmp_path) / "report.json"
    commands = [
        ("request", GOOD / "request_pack.json"),
        ("brief", GOOD / "sampling_brief.json", "--request", GOOD / "request_pack.json"),
        ("spec", GOOD / "sampling_spec.json", "--brief", GOOD / "sampling_brief.json",
         "--request", GOOD / "request_pack.json", "--require-approved"),
        ("report", GOOD / "coverage_report.json", "--spec", GOOD / "sampling_spec.json",
         "--sample-dir", GOOD / "sample"),
        ("verify", "--spec", GOOD / "sampling_spec.json", "--sample-dir", GOOD / "sample",
         "--ticket", "DEMO-123", "--out", out_file),
    ]
    for command in commands:
        code, out, _ = run_cli(*command)
        assert code == 0, (command[0], out)
    assert json.loads(out_file.read_text("utf-8")) == load("coverage_report.json")


@pytest.mark.ts13
def test_ts13_verify_prints_the_report_when_no_output_file_is_given():
    code, out, _ = run_cli("verify", "--spec", GOOD / "sampling_spec.json",
                           "--sample-dir", GOOD / "sample", "--ticket", "DEMO-123")
    assert code == 0
    assert '"total_rows": 48' in out


@pytest.mark.ts13
def test_ts13_json_output_is_machine_readable():
    code, out, _ = run_cli("--json", "request", GOOD / "request_pack.json")
    assert code == 0
    assert json.loads(out) == {"artifact": "request pack", "findings": []}
    code, out, _ = run_cli("--json", "verify", "--spec", GOOD / "sampling_spec.json",
                           "--sample-dir", GOOD / "sample", "--ticket", "DEMO-123")
    assert json.loads(out)["findings"] == []


@pytest.mark.ts13
def test_ts13_unreadable_input_exits_with_2(tmp_path):
    code, _, err = run_cli("request", Path(tmp_path) / "missing.json")
    assert code == 2 and "[ERROR]" in err
    broken = Path(tmp_path) / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert run_cli("request", broken)[0] == 2


@pytest.mark.ts13
def test_ts13_unknown_match_operator_exits_with_2(tmp_path):
    run = copy_run(tmp_path)
    edit(run, "sampling_spec.json",
         lambda s: s["scenarios"][0]["match"]["conditions"][0].update(op="near"))
    code, _, err = run_cli("verify", "--spec", run / "sampling_spec.json",
                           "--sample-dir", run / "sample", "--ticket", "DEMO-123")
    assert code == 2 and "unknown operator" in err


@pytest.mark.ts13
def test_ts13_exit_codes_work_from_a_real_shell(tmp_path):
    base = [sys.executable, "-m", "sampling_validator.cli", "check-run"]
    good = subprocess.run(base + [str(GOOD)], env=ENV, capture_output=True, text=True)
    assert good.returncode == 0
    run = copy_run(tmp_path)
    edit(run, "request_pack.json", lambda p: p.pop("constraints"))
    bad = subprocess.run(base + [str(run)], env=ENV, capture_output=True, text=True)
    assert bad.returncode == 1 and "REQ-001" in bad.stdout


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    block = text.split("---")[1]
    return dict(line.split(": ", 1) for line in block.strip().splitlines())


@pytest.mark.ts14
def test_ts14_skill_metadata_is_valid():
    skill = ROOT / "skill" / "test-sampling-agent"
    meta = frontmatter(skill / "SKILL.md")
    assert meta["name"] == "test-sampling-agent"
    assert 0 < len(meta["description"]) <= 1024
    assert "<" not in meta["description"] and ">" not in meta["description"]
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for ref in ("references/artifact_schemas.md", "references/edge_case_catalog.md"):
        assert ref in text and (skill / ref).is_file()


@pytest.mark.ts14
def test_ts14_skill_wrapper_runs_the_validators_from_the_repository():
    wrapper = ROOT / "skill" / "test-sampling-agent" / "scripts" / "sampling.py"
    done = subprocess.run([sys.executable, str(wrapper), "check-run", str(GOOD)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.ts14
def test_ts14_built_skill_is_self_contained(tmp_path):
    build = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_skill.py"),
                            "--out", str(tmp_path), "--tag", "v0.0.0"],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    archive = Path(tmp_path) / "test-sampling-agent-v0.0.0.skill"
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        bundle.extractall(tmp_path)
    for expected in ("SKILL.md", "scripts/sampling_validator/cli.py",
                     "assets/example_run/sampling_spec.json", "references/artifact_schemas.md"):
        assert f"test-sampling-agent/{expected}" in names
    unpacked = Path(tmp_path) / "test-sampling-agent"
    done = subprocess.run(
        [sys.executable, "scripts/sampling.py", "check-run", "assets/example_run"],
        cwd=unpacked, capture_output=True, text=True)
    assert done.returncode == 0 and "RESULT: PASS" in done.stdout
