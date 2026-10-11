"""Read and write MAC addresses in the common vendor formats, and convert pasted lists between them.

Supported output formats (lowercase by default, uppercase on request):

    colon   aa:bb:cc:dd:ee:ff    Linux, most vendors
    hyphen  aa-bb-cc-dd-ee-ff    Windows
    dotted  aabb.ccdd.eeff       Cisco

Input also accepts bare 12 hex digits (aabbccddeeff), and any mix of upper/lower case.

Inside this module a MAC is held as a plain integer (48 bits). That makes formatting a matter of
printing the number as 12 hex digits and cutting them into groups, and it makes the generator's bit
twiddling simple. Think of the integer as the MAC "itself" and the formats as different ways of
writing it down.

Pure Python, no web code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The keys the web form sends, in the order they're offered.
FORMATS = ("colon", "hyphen", "dotted")

# Patterns for the input forms we accept. Each is "the whole string", thanks to fullmatch() below.
#   [0-9a-fA-F]{2}  = exactly two hex digits
#   ([:-])  then \1 = the first separator found, and the same one again later (no mixing : and -)
_SIX_PAIRS = re.compile(r"[0-9a-fA-F]{2}([:-])(?:[0-9a-fA-F]{2}\1){4}[0-9a-fA-F]{2}")
_CISCO_DOTTED = re.compile(r"(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}")
_BARE = re.compile(r"[0-9a-fA-F]{12}")


class MACError(ValueError):
    """A MAC we can't read or a request we can't fulfil. The message is safe to show the user."""


@dataclass
class ConversionResult:
    """What convert_lines() produced: the converted MACs, plus the lines it couldn't read.

    `errors` holds (line number, original text) pairs so the page can say exactly which lines were
    skipped instead of silently dropping them.
    """

    converted: list[str] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class AllFormatsResult:
    """What convert_all_formats() produced: the same MACs written in every format.

    `by_format` maps each format key to its list, e.g. {"colon": [...], "hyphen": [...], ...}, in the
    order of FORMATS. `errors` is as in ConversionResult.
    """

    by_format: dict[str, list[str]] = field(default_factory=dict)
    errors: list[tuple[int, str]] = field(default_factory=list)


def parse_mac(text: str) -> int:
    """Read one MAC in any accepted form and return it as a 48-bit integer."""
    text = text.strip()
    if not (_SIX_PAIRS.fullmatch(text) or _CISCO_DOTTED.fullmatch(text) or _BARE.fullmatch(text)):
        raise MACError(
            f"'{text}' isn't a MAC address. Use e.g. aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, "
            "aabb.ccdd.eeff or aabbccddeeff."
        )
    # The pattern check proved it's 12 hex digits plus separators, so drop the separators and read
    # the hex digits as one base-16 number.
    digits = re.sub(r"[:.-]", "", text)
    return int(digits, 16)


def format_mac(value: int, style: str = "colon", upper: bool = False) -> str:
    """Write a 48-bit integer as a MAC in the chosen style."""
    if style not in FORMATS:
        raise MACError(f"Unknown MAC format '{style}'. Choose one of: {', '.join(FORMATS)}.")
    if not 0 <= value < 2**48:
        raise MACError(f"{value} doesn't fit in a MAC address (48 bits).")

    # f"{value:012x}" = hex, lowercase, padded with leading zeros to 12 digits.
    digits = f"{value:012x}"
    if upper:
        digits = digits.upper()

    if style == "dotted":
        # Three groups of four: aabb.ccdd.eeff
        return ".".join(digits[i : i + 4] for i in range(0, 12, 4))
    # Six groups of two, joined with ":" or "-".
    separator = ":" if style == "colon" else "-"
    return separator.join(digits[i : i + 2] for i in range(0, 12, 2))


def parse_lines(text: str) -> tuple[list[int], list[tuple[int, str]]]:
    """Read a pasted block of MACs (one per line).

    Returns the MACs that could be read (as integers, in paste order) and the lines that couldn't,
    as (line number, text) pairs. Line numbers count from 1, as a person would. Blank lines are
    skipped without complaint.
    """
    values: list[int] = []
    errors: list[tuple[int, str]] = []
    # enumerate(..., start=1) numbers the lines 1, 2, 3...; splitlines() copes with Windows and
    # Linux line endings alike.
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            values.append(parse_mac(line))
        except MACError:
            errors.append((line_number, line.strip()))
    return values, errors


def convert_lines(text: str, style: str = "colon", upper: bool = False) -> ConversionResult:
    """Convert a pasted block of MACs (one per line) to one chosen style.

    Blank lines are skipped; lines that aren't MACs are reported in `errors` and the rest are still
    converted.
    """
    # Check the style once up front, so a bad style is one clear error rather than one per line.
    if style not in FORMATS:
        raise MACError(f"Unknown MAC format '{style}'. Choose one of: {', '.join(FORMATS)}.")
    values, errors = parse_lines(text)
    return ConversionResult(converted=[format_mac(v, style, upper) for v in values], errors=errors)


def convert_all_formats(text: str, upper: bool = False) -> AllFormatsResult:
    """Convert a pasted block of MACs into every format at once (the converter page shows them all).

    Each line is parsed once, then written out once per format.
    """
    values, errors = parse_lines(text)
    by_format = {style: [format_mac(v, style, upper) for v in values] for style in FORMATS}
    return AllFormatsResult(by_format=by_format, errors=errors)
