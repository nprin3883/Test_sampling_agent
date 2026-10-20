#!/usr/bin/env python3
"""Build the uploadable skill: python3 scripts/build_skill.py --out dist [--tag v0.1.0]

Bundles skill/test-sampling-agent with the validators from src/ (single source of truth) and the
synthetic example run, then zips it as <name>[-tag].skill.
"""
import argparse
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "test-sampling-agent"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def check_frontmatter(skill_md: Path) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", skill_md.read_text(encoding="utf-8"), re.S)
    if not match:
        raise SystemExit("SKILL.md has no frontmatter")
    fields = dict(re.findall(r"^(name|description): (.+)$", match.group(1), re.M))
    name, description = fields.get("name", ""), fields.get("description", "")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        raise SystemExit(f"invalid skill name: {name!r}")
    if not description or len(description) > 1024 or "<" in description or ">" in description:
        raise SystemExit("description must be 1-1024 characters without angle brackets")
    return name


def build(out_dir: Path, tag: str = "") -> Path:
    name = check_frontmatter(SKILL / "SKILL.md")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / name
        shutil.copytree(SKILL, stage, ignore=IGNORE)
        shutil.copytree(ROOT / "src" / "sampling_validator",
                        stage / "scripts" / "sampling_validator", ignore=IGNORE)
        shutil.copytree(ROOT / "tests" / "fixtures" / "good_run", stage / "assets" / "example_run")
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / (f"{name}-{tag}.skill" if tag else f"{name}.skill")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(name) / path.relative_to(stage))
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    print(build(Path(args.out), args.tag))


if __name__ == "__main__":
    main()
