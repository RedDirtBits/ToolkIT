"""Read IEEE's MAC address registries and look up who a MAC belongs to (and the reverse).

IEEE hands out the first part of MAC addresses to companies, in three block sizes. Each has its own
CSV file on IEEE's site:

    block  file        prefix length              addresses per block   example prefix
    MA-L   oui.csv     24 bits (6 hex digits)     16.7 million          00:1A:2B
    MA-M   mam.csv     28 bits (7 hex digits)     1 million             C8:5C:E2:7
    MA-S   oui36.csv   36 bits (9 hex digits)     4,096                 8C:1F:64:AF:A

The small blocks are carved out of big ones that IEEE keeps for itself (listed in oui.csv as "IEEE
Registration Authority"). So a lookup tries the longest prefix first, like a router's
longest-match: MA-S, then MA-M, then MA-L.

Every CSV has the same four columns: Registry, Assignment, Organization Name, Organization Address.

Before the list is even needed, two bits in the first byte can already answer the question:
- multicast bit set     -> a group address, not a device;
- local bit set         -> "locally administered": set by software (phones' randomized private
                           MACs, VMs, ToolkIT's own fakes), never assigned to a vendor.

Pure Python, no web code and no network: oui_update.py fetches the files.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from app.tools.mac_format import format_mac

# Block name -> (file name on IEEE's site and in data/, hex digits in its prefixes).
BLOCKS = {
    "MA-S": ("oui36.csv", 9),
    "MA-M": ("mam.csv", 7),
    "MA-L": ("oui.csv", 6),
}  # longest prefix first: that's the order lookups try them in

# The header line every IEEE registry CSV starts with.
HEADER = ["Registry", "Assignment", "Organization Name", "Organization Address"]

# What IEEE writes as the name when a company paid to keep its listing private.
PRIVATE_NAME = "Private"

# The owner IEEE lists for the big blocks it splits into MA-M and MA-S blocks.
IEEE_RA_NAME = "IEEE Registration Authority"

# Shortest vendor search allowed: one letter would match nearly everything.
MIN_SEARCH_LENGTH = 2

# One line's verdict, as kept in LookupResult.kind:
#   vendor     found in the list
#   private    found, but the owner's name is withheld
#   local      locally administered (no vendor by definition)
#   multicast  a group address (includes broadcast)
#   unknown    a normal address that isn't in the list
#   invalid    not a MAC or prefix at all
KIND_LABELS = {
    "private": "Private (registered, owner's name withheld by IEEE)",
    "local": "Locally administered (randomized or set by software; no vendor)",
    "multicast": "Multicast (a group address, not a device)",
    "unknown": "Not in the IEEE list",
    "invalid": "(not a MAC address)",
}


class OUIDataError(ValueError):
    """A file or request we can't use. The message is written for the user and is safe to show."""


@dataclass(frozen=True)
class Assignment:
    """One registered block: its prefix (uppercase hex, 6/7/9 digits), size and owner."""

    prefix: str
    block: str
    vendor: str

    @property
    def bits(self) -> int:
        """Prefix length in bits: 24, 28 or 36 (each hex digit is 4 bits)."""
        return len(self.prefix) * 4

    def format_prefix(self, style: str = "colon", upper: bool = False) -> str:
        """Write the prefix the way it's usually seen.

        MA-L (24 bits) is written short, as people do:  00:1a:2b   00-1a-2b   001a.2b
        MA-M and MA-S end mid-byte, so they're written as a full MAC with the prefix length (the
        same notation Wireshark uses):                  c8:5c:e2:70:00:00/28
        """
        if self.bits == 24:
            digits = self.prefix if upper else self.prefix.lower()
            if style == "dotted":
                return f"{digits[:4]}.{digits[4:]}"
            separator = "-" if style == "hyphen" else ":"
            return separator.join(digits[i : i + 2] for i in range(0, 6, 2))
        # Pad the prefix with zeros to 12 hex digits and write it as a MAC.
        value = int(self.prefix.ljust(12, "0"), 16)
        return f"{format_mac(value, style, upper)}/{self.bits}"


@dataclass(frozen=True)
class LookupResult:
    """The answer for one input line. `label` is what the page shows in the vendor column."""

    text: str
    kind: str
    label: str
    assignment: Assignment | None = None


class OUIDatabase:
    """All three registries in memory, ready for lookups and searches.

    About 54,000 entries: a few MB of memory, and a lookup is three dictionary checks.
    """

    def __init__(self, assignments: list[Assignment]) -> None:
        # One dict per block: prefix -> Assignment. A dict answers "is this key here?" instantly,
        # however many entries it holds.
        self.by_block: dict[str, dict[str, Assignment]] = {block: {} for block in BLOCKS}
        for entry in assignments:
            self.by_block[entry.block][entry.prefix] = entry

    def __len__(self) -> int:
        return sum(len(entries) for entries in self.by_block.values())

    def counts(self) -> dict[str, int]:
        """How many entries each block has, e.g. {"MA-L": 40316, ...}; 0 if its file is missing."""
        return {block: len(entries) for block, entries in self.by_block.items()}

    def find(self, value: int, known_bits: int = 48) -> Assignment | None:
        """The longest registered prefix matching a MAC (as a 48-bit integer).

        `known_bits` is how much of `value` the user actually gave: a bare prefix like 00:1a:2b is
        24 bits, so a 28- or 36-bit block can't be matched from it (the digits that would decide
        it are missing).
        """
        digits = f"{value:012X}"  # 12 uppercase hex digits, like the CSVs use
        for block, (_, length) in BLOCKS.items():
            if length * 4 > known_bits:
                continue
            entry = self.by_block[block].get(digits[:length])
            if entry is not None:
                return entry
        return None

    def search(self, text: str) -> list[Assignment]:
        """Every block whose vendor name contains `text` (ignoring case), sorted by vendor, prefix."""
        needle = text.strip().casefold()
        if len(needle) < MIN_SEARCH_LENGTH:
            raise OUIDataError(f"Type at least {MIN_SEARCH_LENGTH} characters of the vendor name.")
        matches = [
            entry
            for entries in self.by_block.values()
            for entry in entries.values()
            if needle in entry.vendor.casefold()
        ]
        # A "sort key" function: sort by vendor name first, then by prefix.
        return sorted(matches, key=lambda entry: (entry.vendor.casefold(), entry.prefix))


# --- reading the CSV files -------------------------------------------------------------------------


def parse_registry_csv(text: str) -> tuple[str, list[Assignment]]:
    """Read one IEEE registry CSV. Returns its block ("MA-L"...) and its entries.

    Checks that it really is one: the right header, one block per file, prefixes of the right
    length. That matters for the Import button, where any file could be handed in. A prefix listed
    more than once (a few very old ones have several owners) gets all the names, joined with " / ".
    """
    try:
        return _parse_rows(text)
    except csv.Error as error:
        # The csv module's own complaints (e.g. a quote that's never closed makes one "field" run
        # past its 128 KB limit) aren't OUIDataError, so nothing above would catch them. Turn
        # them into one, so a bad file is reported like any other bad file.
        raise OUIDataError(f"That isn't a readable CSV file ({error}).") from None


def _parse_rows(text: str) -> tuple[str, list[Assignment]]:
    """The work of parse_registry_csv(); csv.Error from here is turned into OUIDataError there."""
    # The csv module copes with quoted names that contain commas ("Nokia, Ltd."). io.StringIO
    # makes the text look like an open file, which is what csv.reader expects.
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))  # ﻿: a "BOM" some editors add
    header = next(reader, None)
    if header != HEADER:
        raise OUIDataError(
            "That isn't an IEEE registry CSV (the first line should be "
            f"'{','.join(HEADER)}'). Use oui.csv, mam.csv or oui36.csv from standards-oui.ieee.org."
        )

    names: dict[str, list[str]] = {}  # prefix -> owner name(s), in file order
    block = None
    for row_number, row in enumerate(reader, start=2):
        if not row:
            continue
        if len(row) < 3:
            raise OUIDataError(f"Line {row_number} of the file has too few columns.")
        registry, prefix, vendor = row[0].strip(), row[1].strip().upper(), row[2].strip()
        if block is None:
            if registry not in BLOCKS:
                raise OUIDataError(f"Unknown registry '{registry}' on line {row_number}.")
            block = registry
        if registry != block:
            raise OUIDataError(f"Line {row_number} mixes registries ({registry} in a {block} file).")
        length = BLOCKS[block][1]
        if not re.fullmatch(f"[0-9A-F]{{{length}}}", prefix):
            raise OUIDataError(f"Line {row_number}: '{prefix}' isn't a {length}-digit {block} prefix.")
        owners = names.setdefault(prefix, [])
        if vendor and vendor not in owners:
            owners.append(vendor)

    if block is None:
        raise OUIDataError("That file has a header but no entries.")
    entries = [
        Assignment(prefix=prefix, block=block, vendor=" / ".join(owners) or PRIVATE_NAME)
        for prefix, owners in names.items()
    ]
    return block, entries


def load_folder(folder: Path) -> OUIDatabase | None:
    """Load whichever of the three registry files are in `folder`. None if there are none at all."""
    entries: list[Assignment] = []
    found = False
    for file_name, _ in BLOCKS.values():
        path = folder / file_name
        if path.is_file():
            found = True
            # newline="" lets the csv module see line endings inside quoted fields itself.
            with path.open(encoding="utf-8", newline="") as handle:
                entries += parse_registry_csv(handle.read())[1]
    return OUIDatabase(entries) if found else None


# --- looking up what the user typed -------------------------------------------------------------


def lookup_text(line: str, db: OUIDatabase) -> LookupResult:
    """Look up one line: a full MAC in any format, or a bare prefix such as 00:1a:2b or 001a2b."""
    text = line.strip()
    # Drop the usual separators; what's left must be 6 to 12 hex digits.
    digits = re.sub(r"[:.\-\s]", "", text)
    if not re.fullmatch(r"[0-9A-Fa-f]{6,12}", digits):
        return LookupResult(text, "invalid", KIND_LABELS["invalid"])

    # Pad a prefix out to a full 12 digits so the bit checks below work the same for both.
    value = int(digits.ljust(12, "0"), 16)
    first_byte = value >> 40
    if first_byte & 0b01:
        return LookupResult(text, "multicast", KIND_LABELS["multicast"])
    if first_byte & 0b10:
        return LookupResult(text, "local", KIND_LABELS["local"])

    entry = db.find(value, known_bits=len(digits) * 4)
    if entry is None:
        return LookupResult(text, "unknown", KIND_LABELS["unknown"])
    if entry.vendor == PRIVATE_NAME:
        return LookupResult(text, "private", KIND_LABELS["private"], entry)
    if entry.vendor == IEEE_RA_NAME and len(digits) < 12:
        # A bare prefix inside a block IEEE split up: the real owner depends on digits not given.
        label = f"{IEEE_RA_NAME} (split into smaller blocks: give the full MAC to see the owner)"
        return LookupResult(text, "vendor", label, entry)
    return LookupResult(text, "vendor", entry.vendor, entry)


def lookup_lines(text: str, db: OUIDatabase) -> list[LookupResult | None]:
    """Look up every line of a paste. Blank lines give None, so results line up row for row."""
    return [lookup_text(line, db) if line.strip() else None for line in text.splitlines()]
