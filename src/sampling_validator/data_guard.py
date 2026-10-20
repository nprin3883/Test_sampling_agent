"""Heuristic guard: artifacts and samples must not carry raw personal data."""
from __future__ import annotations

import re

from .findings import Finding, err

EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.)+[A-Za-z]{2,}")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
LONG_NUMBER = re.compile(r"\b\d{13,19}\b")
SAFE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
FORBIDDEN_KEYS = ("raw_records", "records", "rows", "sample_rows", "sample_values")


def suspicious(text: str) -> str | None:
    """Return the kind of personal data a string looks like, else None."""
    for match in EMAIL.finditer(text):
        if not match.group(0).lower().endswith(SAFE_EMAIL_DOMAINS):
            return "e-mail address"
    if IBAN.search(text):
        return "IBAN-like value"
    if LONG_NUMBER.search(text):
        return "card-number-like value"
    return None


def scan_artifact(obj, where: str = "") -> list[Finding]:
    """Walk a JSON artifact looking for raw records and personal-data patterns."""
    out: list[Finding] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{where}.{key}" if where else key
            if key in FORBIDDEN_KEYS and value:
                out.append(err("DAT-001", f"key '{key}' suggests raw records inside an artifact",
                               path))
            out += scan_artifact(value, path)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            out += scan_artifact(value, f"{where}[{idx}]")
    elif isinstance(obj, str):
        kind = suspicious(obj)
        if kind:
            out.append(err("DAT-001", f"value looks like an {kind}: mask or remove it", where))
    return out


def scan_sample(sample: dict[str, list[dict]]) -> list[Finding]:
    """Extracted samples must be masked according to the data-handling rules."""
    out: list[Finding] = []
    for table, rows in sample.items():
        flagged = set()
        for row in rows:
            for column, value in row.items():
                kind = suspicious(str(value or ""))
                if kind and column not in flagged:
                    flagged.add(column)
                    out.append(err("DAT-002", f"unmasked {kind} in the extracted sample",
                                   f"{table}.{column}"))
    return out
