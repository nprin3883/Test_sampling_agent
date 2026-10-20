"""Findings reported by the checks."""
from __future__ import annotations

from dataclasses import asdict, dataclass

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    severity: str = ERROR
    where: str = ""

    def __str__(self) -> str:
        location = f" [{self.where}]" if self.where else ""
        return f"{self.severity.upper():7} {self.code}{location}: {self.message}"

    def as_dict(self) -> dict:
        return asdict(self)


def err(code: str, message: str, where: str = "") -> Finding:
    return Finding(code, message, ERROR, where)


def warn(code: str, message: str, where: str = "") -> Finding:
    return Finding(code, message, WARNING, where)


def has_errors(findings: list[Finding]) -> bool:
    return any(f.severity == ERROR for f in findings)


def codes(findings: list[Finding]) -> set[str]:
    return {f.code for f in findings}
