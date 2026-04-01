from __future__ import annotations

import re
from datetime import date, datetime, time
from email.utils import parsedate_to_datetime


SUPPORTED_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
)


def normalize_name(raw_name: str) -> str:
    name = raw_name.strip().lower()
    if not name:
        return ""

    if "," in name:
        parts = [part.strip() for part in name.split(",")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"
        else:
            name = " ".join(p for p in parts if p)

    name = name.replace(",", " ")
    name = " ".join(name.split())
    return name


def normalize_date(raw_date: str) -> date:
    candidate = raw_date.strip()
    if not candidate:
        raise ValueError("date is empty")

    # Accept trailing Z by converting to +00:00.
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
        return datetime.fromisoformat(candidate).date()

    try:
        return datetime.fromisoformat(candidate).date()
    except ValueError:
        pass

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date format: {raw_date}")


# ---------------------------------------------------------------------------
# Time normalization
# ---------------------------------------------------------------------------


def parse_wiw_datetime(raw: str) -> datetime | None:
    """Parse When I Work datetime: 'Fri, 27 Mar 2026 17:30:00 -0400'."""
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return None


def normalize_time(hour: int, minute: int, ampm: str = "") -> time | None:
    """Convert hour/minute/ampm to a time object."""
    h = hour
    ap = ampm.strip().upper()
    if ap == "PM" and h != 12:
        h += 12
    elif ap == "AM" and h == 12:
        h = 0
    if 0 <= h <= 23 and 0 <= minute <= 59:
        return time(h, minute)
    return None


def times_match(
    t1_start: time | None,
    t1_end: time | None,
    t2_start: time | None,
    t2_end: time | None,
    tolerance_minutes: int = 30,
) -> bool:
    """Check if two time ranges are within tolerance of each other."""
    if t1_start is None or t2_start is None:
        return False

    def minutes_diff(a: time, b: time) -> int:
        a_min = a.hour * 60 + a.minute
        b_min = b.hour * 60 + b.minute
        return abs(a_min - b_min)

    start_ok = minutes_diff(t1_start, t2_start) <= tolerance_minutes

    if t1_end is not None and t2_end is not None:
        end_ok = minutes_diff(t1_end, t2_end) <= tolerance_minutes
        return start_ok and end_ok

    return start_ok


# ---------------------------------------------------------------------------
# Client alias registry
# ---------------------------------------------------------------------------

# Pattern to strip parenthetical suffixes: "Cody (Cliffside)" -> "Cody"
_PAREN_PATTERN = re.compile(r"\s*\(.*?\)\s*$")
# Pattern to strip business suffixes: "Name - Business" -> "Name"
_BUSINESS_PATTERN = re.compile(r"\s*-\s+\S.*$")


# Common nickname mappings for first names
_NICKNAMES: dict[str, str] = {
    "patty": "patricia",
    "pat": "patricia",
    "chris": "christopher",
    "mike": "michael",
    "ed": "edward",
    "eddy": "edward",
    "eddie": "edward",
    "matt": "matthew",
    "dan": "daniel",
    "danny": "daniel",
    "bob": "robert",
    "rob": "robert",
    "jim": "james",
    "jimmy": "james",
    "joe": "joseph",
    "joey": "joseph",
    "tom": "thomas",
    "tommy": "thomas",
    "bill": "william",
    "billy": "william",
    "beth": "bethany",
    "kate": "katherine",
    "katie": "katherine",
    "liz": "elizabeth",
    "nick": "nicholas",
    "tony": "anthony",
    "steve": "stephen",
    "stew": "stewart",
    "marty": "martin",
    "jay": "jason",
    "dom": "domenico",
}


class ClientAliasRegistry:
    """Maps various name forms to canonical billing names.

    Canonical names come from billing files (most authoritative).
    Aliases are generated to match When I Work site names and JotForm client names.
    """

    def __init__(self) -> None:
        self._canonical: dict[str, str] = {}      # normalized_alias -> canonical_name
        self._first_name_index: dict[str, list[str]] = {}  # first_name -> [canonical_names]

    def add_alias(self, alias: str, canonical: str) -> None:
        """Add a manual alias mapping."""
        self._canonical[alias.strip().lower()] = canonical.strip().lower()

    def seed_from_billing(self, canonical_names: set[str]) -> None:
        """Seed the registry with canonical names from billing data."""
        for name in canonical_names:
            normalized = name.strip().lower()
            if not normalized:
                continue
            # Map exact form
            self._canonical[normalized] = normalized

            # Generate aliases
            parts = normalized.split()
            if len(parts) >= 2:
                first = parts[0]
                last = parts[-1]
                # "first l." abbreviation
                self._canonical[f"{first} {last[0]}."] = normalized
                # Index by first name for fuzzy matching
                self._first_name_index.setdefault(first, []).append(normalized)

                # Add nickname aliases: "patty emanuele" -> "patricia emanuele"
                for nick, formal in _NICKNAMES.items():
                    if formal == first:
                        nick_form = f"{nick} {last}"
                        if nick_form not in self._canonical:
                            self._canonical[nick_form] = normalized
                        nick_abbrev = f"{nick} {last[0]}."
                        if nick_abbrev not in self._canonical:
                            self._canonical[nick_abbrev] = normalized
                        self._first_name_index.setdefault(nick, []).append(normalized)

    def resolve(self, raw_name: str) -> str:
        """Resolve a name to its canonical form, or return normalized as-is."""
        normalized = normalize_name(raw_name) if raw_name else ""
        if not normalized:
            return ""

        # Exact match
        if normalized in self._canonical:
            return self._canonical[normalized]

        # Strip parenthetical suffix: "cody (cliffside)" -> "cody"
        stripped = _PAREN_PATTERN.sub("", normalized).strip()
        if stripped and stripped != normalized:
            if stripped in self._canonical:
                return self._canonical[stripped]
            # Try first-name-only match on stripped form
            stripped_parts = stripped.split()
            if len(stripped_parts) == 1 and stripped in self._first_name_index:
                candidates = self._first_name_index[stripped]
                if len(candidates) == 1:
                    return candidates[0]

        # Strip business suffix: "name - business" -> try match
        stripped_biz = _BUSINESS_PATTERN.sub("", normalized).strip()
        if stripped_biz and stripped_biz != normalized and stripped_biz in self._canonical:
            return self._canonical[stripped_biz]

        # Two-word name: first-name-only match (only if unambiguous)
        parts = normalized.split()
        first = parts[0] if parts else ""
        if first and first in self._first_name_index:
            candidates = self._first_name_index[first]
            if len(candidates) == 1:
                # Only match if the raw name is clearly a short form (1-2 words)
                # Don't match multi-word names like "jason plants" to "jason brunty"
                if len(parts) <= 1:
                    return candidates[0]
                # If 2 words and second word looks like abbreviation (ends with .)
                if len(parts) == 2 and parts[1].endswith("."):
                    return candidates[0]

        return normalized
