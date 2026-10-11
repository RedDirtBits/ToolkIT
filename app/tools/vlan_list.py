"""Expand and compress VLAN lists: "10,20-23,100" <-> one VLAN per line.

Input is any mix of VLAN numbers and ranges, separated by commas, spaces or new lines:

    10,20-23,100                    compressed (as in a Cisco trunk config line)
    2 3 4 5 6 7 8 85 86 ...         space-separated, possibly wrapped over many lines
    10                              one per line (e.g. a spreadsheet column)
    20
    ...

Every item must be a VLAN number or a range; anything else is reported as invalid, never guessed
at or silently dropped. Valid VLANs are 1 to 4094. Duplicates and overlapping ranges are merged.

Out come the same VLANs two ways: compressed (consecutive VLANs joined into ranges) and expanded
(one per line), always sorted. Plus the FREE VLANs: the unused IDs between the lowest and highest
VLAN in the list (handy when picking IDs for new subnets). Everything above the highest is free
too, but that's obvious and would only add one big range at the end.

Pure Python, no web code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_VLAN = 1
MAX_VLAN = 4094

# An item: one number, or two numbers joined by a dash (spaces around the dash are tidied away
# before splitting, see parse_vlans()).
_ITEM = re.compile(r"(\d+)(?:-(\d+))?")


class VLANListError(ValueError):
    """A request we can't fulfil. The message is written for the user and is safe to show as-is."""


@dataclass
class VLANResult:
    """What parse_vlans() found.

    vlans    every valid VLAN, sorted, no duplicates
    items    how many items (numbers or ranges) were read, valid or not
    invalid  (item text, reason) for each item that isn't a usable VLAN or range
    """

    vlans: list[int] = field(default_factory=list)
    items: int = 0
    invalid: list[tuple[str, str]] = field(default_factory=list)


def parse_vlans(text: str) -> VLANResult:
    """Read every VLAN number and range in a paste (see the module docstring)."""
    # "20 - 23" -> "20-23", so a spaced-out range isn't split into three items.
    tidied = re.sub(r"\s*-\s*", "-", text)
    # Split on any run of commas and whitespace (new lines included); drop empty pieces.
    items = [item for item in re.split(r"[,\s]+", tidied) if item]
    if not items:
        raise VLANListError("Paste some VLANs: e.g. 10,20-23,100 or one per line.")

    result = VLANResult(items=len(items))
    found: set[int] = set()
    for item in items:
        match = _ITEM.fullmatch(item)
        if not match:
            result.invalid.append((item, "not a VLAN number or range"))
            continue
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start > end:
            result.invalid.append((item, "range runs backwards (write it low-high)"))
            continue
        if start < MIN_VLAN or end > MAX_VLAN:
            result.invalid.append((item, f"outside {MIN_VLAN}-{MAX_VLAN}"))
            continue
        # A set ignores repeats, so overlapping ranges and duplicates merge by themselves.
        found.update(range(start, end + 1))

    result.vlans = sorted(found)
    return result


def free_vlans(vlans: list[int]) -> list[int]:
    """The unused VLAN IDs between the lowest and highest of `vlans` (sorted, unique).

    [10, 20, 21, 23] -> [11, 12, ..., 19, 22]. Fewer than two VLANs have no gaps between them.
    """
    if len(vlans) < 2:
        return []
    used = set(vlans)
    return [vlan for vlan in range(vlans[0] + 1, vlans[-1]) if vlan not in used]


def compress(vlans: list[int]) -> str:
    """Write sorted, unique VLANs compactly: [10, 20, 21, 22, 23, 100] -> "10,20-23,100".

    Walks the list once, extending the current range while each VLAN is one more than the last,
    and writing the range out when the run breaks. A run of two is written as a range too
    ("85-86"): every switch that reads ranges accepts it.
    """
    if not vlans:
        return ""
    parts: list[str] = []
    start = previous = vlans[0]
    for vlan in vlans[1:]:
        if vlan == previous + 1:
            previous = vlan  # still consecutive: extend the run
            continue
        parts.append(_run(start, previous))
        start = previous = vlan
    parts.append(_run(start, previous))
    return ",".join(parts)


def _run(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"
