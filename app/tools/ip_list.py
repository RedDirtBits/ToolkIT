"""Clean up a pasted list of IPv4 addresses and networks: deduplicate, sort, summarize.

Each line is one item, read as a whole:

    192.168.4.17                  an address
    192.168.4.0/24                a network (no host bits set)
    192.168.4.0 255.255.255.0     a network, mask after a space (or a slash)
    192.168.4.0 0.0.0.255         a network, ACL wildcard
    192.168.4.17/24               an ADDRESS: host bits set means interface notation, i.e. .17 itself

Blank lines are skipped; anything else is reported as invalid, never dropped silently. Internally
every item is an IPv4Network, an address being a /32, so all the comparisons work the same way.

What comes out (all at once):
- unique items in their original order;
- unique items sorted numerically (.2 before .10, unlike a text sort);
- the fewest CIDR blocks covering EXACTLY the input (for ACLs and prefix lists);
- the smallest single block covering everything, and how many extra addresses it would include.

Pure Python, no web code. The mask/wildcard reading is shared with the subnet calculator.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from app.tools.subnet_calc import SubnetError, parse_input, read_as_single_host

# Same per-request limit as the other tools, so a giant paste can't hang the page.
MAX_LINES = 65_534

# How summarized blocks can be written. The keys are what the web form sends.
#   prefix    192.168.4.0/22
#   mask      192.168.4.0 255.255.252.0
#   wildcard  192.168.4.0 0.0.3.255        (ready for an ACL)
BLOCK_STYLES = ("prefix", "mask", "wildcard")


class IPListError(ValueError):
    """A request we can't fulfil. The message is written for the user and is safe to show as-is."""


@dataclass
class CleanupResult:
    """What clean_up() found. Lists hold IPv4Networks (an address is a /32).

    total       non-blank lines read
    original    unique items, in the order first seen
    sorted      unique items, numerically sorted
    summary     the fewest blocks covering exactly the input
    covering    the smallest single block containing everything (None if nothing valid)
    extra       addresses inside `covering` that weren't in the input
    invalid     (line number, text) of lines that aren't addresses or networks
    read_as_host  (line number, text) of lines whose mask/wildcard was 0.0.0.0 or 255.255.255.255,
                read as one host (/32) although an ACL might have meant "any" (see subnet_calc)
    """

    total: int = 0
    original: list[ipaddress.IPv4Network] = field(default_factory=list)
    sorted: list[ipaddress.IPv4Network] = field(default_factory=list)
    summary: list[ipaddress.IPv4Network] = field(default_factory=list)
    covering: ipaddress.IPv4Network | None = None
    extra: int = 0
    invalid: list[tuple[int, str]] = field(default_factory=list)
    read_as_host: list[tuple[int, str]] = field(default_factory=list)

    @property
    def duplicates(self) -> int:
        """Valid lines that repeated an earlier one."""
        return self.total - len(self.invalid) - len(self.original)


def parse_item(text: str) -> ipaddress.IPv4Network:
    """Read one line as an address (a /32) or a network. See the module docstring for the rules."""
    text = text.strip()
    try:
        # A bare address: no prefix or mask after it.
        return ipaddress.IPv4Network(ipaddress.IPv4Address(text))
    except ValueError:
        pass
    try:
        interface = parse_input(text)
    except SubnetError as error:
        raise IPListError(str(error)) from None
    if interface.ip != interface.network.network_address:
        # Host bits are set (192.168.4.17/24): the line names that one address.
        return ipaddress.IPv4Network(interface.ip)
    return interface.network


def clean_up(text: str) -> CleanupResult:
    """Read a pasted list (one item per line) and work out every result."""
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise IPListError(f"Paste at most {MAX_LINES:,} lines at a time.")

    result = CleanupResult()
    seen: set[ipaddress.IPv4Network] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        result.total += 1
        try:
            item = parse_item(line)
        except IPListError:
            result.invalid.append((line_number, line.strip()))
            continue
        if read_as_single_host(line):
            # Valid, but possibly not what was meant: the page warns about it.
            result.read_as_host.append((line_number, line.strip()))
        if item not in seen:
            seen.add(item)
            result.original.append(item)

    if not result.total:
        raise IPListError("Paste at least one address or network, one per line.")
    if not result.original:
        return result  # nothing valid: only the invalid list to show

    # Networks sort by their first address, then by size: 192.168.4.0/22 before 192.168.4.0/24.
    result.sorted = sorted(result.original)
    # collapse_addresses merges overlapping and neighbouring blocks into the fewest possible,
    # without adding a single address that wasn't in the input.
    result.summary = list(ipaddress.collapse_addresses(result.original))
    result.covering = covering_block(result.summary)
    covered = sum(block.num_addresses for block in result.summary)
    result.extra = result.covering.num_addresses - covered
    return result


def covering_block(networks: list[ipaddress.IPv4Network]) -> ipaddress.IPv4Network:
    """The smallest single block containing every network given.

    The first and last addresses agree on some number of leading bits; that shared start is the
    block. XOR (^) marks the bits where they differ, and bit_length() says how many bits from the
    right that is, so the prefix is everything to the left of the first difference.
    """
    first = int(min(n.network_address for n in networks))
    last = int(max(n.broadcast_address for n in networks))
    prefix = 32 - (first ^ last).bit_length()
    return ipaddress.IPv4Network((first, prefix), strict=False)


def format_item(network: ipaddress.IPv4Network) -> str:
    """An item as the user would write it: a /32 as a plain address, a network with its prefix."""
    if network.prefixlen == 32:
        return str(network.network_address)
    return str(network)


def format_block(network: ipaddress.IPv4Network, style: str = "prefix") -> str:
    """A summarized block in the chosen style (see BLOCK_STYLES). /32s keep their size, as
    prefix lists and ACLs need it ("192.168.4.17 0.0.0.0" is one host in an ACL)."""
    if style not in BLOCK_STYLES:
        raise IPListError(f"Unknown style '{style}'. Choose one of: {', '.join(BLOCK_STYLES)}.")
    if style == "mask":
        return f"{network.network_address} {network.netmask}"
    if style == "wildcard":
        return f"{network.network_address} {network.hostmask}"
    return str(network)
