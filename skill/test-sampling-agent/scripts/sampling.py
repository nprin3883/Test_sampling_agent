#!/usr/bin/env python3
"""Run the sampling checks: python3 scripts/sampling.py <command> ...

Inside the packaged skill the validators sit next to this file; in the repository they are
imported from src/.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE, HERE.parents[2] / "src"):
    if (candidate / "sampling_validator").is_dir():
        sys.path.insert(0, str(candidate))
        break

from sampling_validator.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
