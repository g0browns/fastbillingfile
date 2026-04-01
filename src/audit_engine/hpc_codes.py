from __future__ import annotations

from pathlib import Path


def _expand_range(range_str: str) -> list[str]:
    """Expand a code range like 'FQW-FQZ' into ['FQW', 'FQX', 'FQY', 'FQZ']."""
    parts = range_str.split("-")
    if len(parts) != 2:
        return [range_str.strip()]
    start, end = parts[0].strip(), parts[1].strip()
    if not start or not end:
        return [range_str.strip()]
    if len(start) != len(end) or start[:-1] != end[:-1]:
        return [range_str.strip()]
    prefix = start[:-1]
    start_char = start[-1]
    end_char = end[-1]
    if not start_char.isalpha() or not end_char.isalpha():
        return [range_str.strip()]
    codes: list[str] = []
    for c in range(ord(start_char), ord(end_char) + 1):
        codes.append(prefix + chr(c))
    return codes


def load_hpc_codes(path: Path) -> frozenset[str]:
    """Load valid HPC service codes from a file, expanding any ranges."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    codes: set[str] = set()
    for line in text.splitlines():
        entry = line.strip().upper()
        if not entry:
            continue
        if "-" in entry:
            codes.update(_expand_range(entry))
        else:
            codes.add(entry)
    return frozenset(codes)


def is_hpc(code: str, hpc_codes: frozenset[str]) -> bool:
    """Check if a service code is a valid HPC code."""
    return code.strip().upper() in hpc_codes
