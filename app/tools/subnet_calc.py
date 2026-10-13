"""IPv4 subnet calculator: everything about the subnet an address is in, and splitting it up.

Input, all meaning the same thing (host bits are fine: ".17" just means "the subnet .17 is in"):

    192.168.4.17/22                 prefix length
    192.168.4.17/255.255.252.0      mask after a slash
    192.168.4.17 255.255.252.0      mask after a space (as in Cisco interface config)
    192.168.4.0 0.0.3.255           wildcard (as in Cisco ACLs)

Mask or wildcard? A mask is ones then zeros (255.255.252.0); a wildcard is the reverse
(0.0.3.255). The shape tells them apart, so the user never has to say which. The two values that
could be either both mean a single host here: 255.255.255.255 as a mask is /32, and 0.0.0.0 as a
wildcard is /32 (ACL "192.0.2.5 0.0.0.0" = exactly that host). Each of them also means "any" when
read the other way (mask 0.0.0.0 = /0, wildcard 255.255.255.255 = /0), so read_as_single_host()
lets the page warn when one of them decided the size.

/31 and /32 are described, not refused: a /31 is a point-to-point link with both addresses usable
and no broadcast (RFC 3021); a /32 is one host.

Splitting: a network into smaller subnets, given either the new prefix ("/26") or how many subnets
are wanted ("8", rounded up to a power of two, because subnets come in halves).

Pure Python, no web code. The standard library's `ipaddress` module does the arithmetic.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

# The most subnets one split may produce (e.g. a /16 into /32s), so a typo can't hang the page.
MAX_SUBNETS = 65_536

# The two sizes that could be a mask or a wildcard. Always read as /32 here (see the docstring).
# Comparing the text is enough: ipaddress only accepts plain dotted decimal (no "000"), so there's
# no other way to write either value.
AMBIGUOUS_SIZES = ("0.0.0.0", "255.255.255.255")

# Address, then the size after it: "/22", "/255.255.252.0" or " 255.255.252.0".
# (\S+?) is the address; (?:/\s*|\s+) is a slash or spaces between; (\S+) is the size.
_ADDRESS_AND_SIZE = re.compile(r"(\S+?)\s*(?:/\s*|\s+)(\S+)")

# What kind of address it is, checked in this order (first match wins). The RFC numbers are where
# each block is defined. 10.0.0.0/8 appears here only so it's recognised as private.
_ADDRESS_TYPES = [
    ("0.0.0.0/8", '"This network" (RFC 791): not a usable address'),
    ("127.0.0.0/8", "Loopback (RFC 1122)"),
    ("169.254.0.0/16", "Link-local (RFC 3927): self-assigned, no DHCP answer"),
    ("224.0.0.0/4", "Multicast (RFC 5771)"),
    ("255.255.255.255/32", "Limited broadcast (RFC 919)"),
    ("240.0.0.0/4", "Reserved (RFC 1112)"),
    ("10.0.0.0/8", "Private (RFC 1918)"),
    ("172.16.0.0/12", "Private (RFC 1918)"),
    ("192.168.0.0/16", "Private (RFC 1918)"),
    ("100.64.0.0/10", "Shared address space / CGNAT (RFC 6598)"),
    ("192.0.2.0/24", "Documentation (RFC 5737)"),
    ("198.51.100.0/24", "Documentation (RFC 5737)"),
    ("203.0.113.0/24", "Documentation (RFC 5737)"),
    ("198.18.0.0/15", "Benchmarking (RFC 2544)"),
    ("192.0.0.0/24", "IETF protocol assignments (RFC 6890)"),
]
_TYPE_NETWORKS = [(ipaddress.IPv4Network(block), label) for block, label in _ADDRESS_TYPES]


class SubnetError(ValueError):
    """Input we can't use. The message is written for the user and is safe to show as-is."""


@dataclass(frozen=True)
class SubnetInfo:
    """Everything about one subnet, worked out from the address the user typed.

    `broadcast` is None for /31 and /32, which have none. `first_usable`..`last_usable` is the
    range of host addresses: all of a /31 or /32, everything between network and broadcast otherwise.
    """

    address: ipaddress.IPv4Address
    network: ipaddress.IPv4Network
    broadcast: ipaddress.IPv4Address | None
    first_usable: ipaddress.IPv4Address
    last_usable: ipaddress.IPv4Address
    usable_hosts: int
    address_type: str

    @property
    def prefix(self) -> int:
        return self.network.prefixlen

    @property
    def netmask(self) -> ipaddress.IPv4Address:
        return self.network.netmask

    @property
    def wildcard(self) -> ipaddress.IPv4Address:
        # ipaddress calls the wildcard the "hostmask": the mask with every bit flipped.
        return self.network.hostmask

    @property
    def total_addresses(self) -> int:
        return self.network.num_addresses


def parse_input(text: str) -> ipaddress.IPv4Interface:
    """Read what the user typed into an address plus its subnet (an IPv4Interface).

    An IPv4Interface is ipaddress's name for "an address together with the network it's on",
    e.g. 192.168.4.17/22: .ip is the address, .network is 192.168.4.0/22.
    """
    text = text.strip()
    if not text:
        raise SubnetError("Type an address with a prefix or mask, e.g. 192.168.4.17/22.")

    match = _ADDRESS_AND_SIZE.fullmatch(text)
    if not match:
        if _is_address(text):
            raise SubnetError(
                f"'{text}' has no prefix or mask. Add one, e.g. {text}/24 or {text} 255.255.255.0."
            )
        raise SubnetError(f"'{text}' isn't an IPv4 address. Use e.g. 192.168.4.17/22.")
    address_text, size_text = match.groups()

    try:
        address = ipaddress.IPv4Address(address_text)
    except ValueError:
        raise SubnetError(f"'{address_text}' isn't an IPv4 address.") from None

    prefix = _read_size(size_text)
    # strict=False is implied for interfaces: host bits are kept as the address.
    return ipaddress.IPv4Interface((address, prefix))


def read_as_single_host(text: str) -> str | None:
    """Which ambiguous size (0.0.0.0 or 255.255.255.255) made `text` a single host, if any.

    Returns that size as typed, or None. Only reports the fact; the page decides how to word the
    warning. Call it on input parse_input() accepted: it doesn't check the address itself.
    """
    match = _ADDRESS_AND_SIZE.fullmatch(text.strip())
    if match and match.group(2) in AMBIGUOUS_SIZES:
        return match.group(2)
    return None


def calculate(text: str) -> SubnetInfo:
    """Work out everything about the subnet in `text` (see parse_input() for accepted forms)."""
    interface = parse_input(text)
    network = interface.network
    if network.prefixlen >= 31:
        # /31: both addresses are hosts (point-to-point). /32: the one address is the host.
        broadcast = None
        first, last = network.network_address, network.broadcast_address
        usable = network.num_addresses
    else:
        broadcast = network.broadcast_address
        # IPv4Address + 1 moves one address on.
        first, last = network.network_address + 1, broadcast - 1
        usable = network.num_addresses - 2
    return SubnetInfo(
        address=interface.ip,
        network=network,
        broadcast=broadcast,
        first_usable=first,
        last_usable=last,
        usable_hosts=usable,
        address_type=address_type(interface.ip),
    )


def address_type(address: ipaddress.IPv4Address) -> str:
    """What kind of address this is: private, public, documentation, loopback..."""
    for network, label in _TYPE_NETWORKS:
        if address in network:
            return label
    return "Public"


def parse_split(text: str) -> tuple[int | None, int | None]:
    """Read the "split into" box: "/26" is a new prefix, "8" a number of subnets.

    Returns (new_prefix, None) or (None, count). Empty input gives (None, None): no split.
    """
    text = text.strip().replace(" ", "")
    if not text:
        return None, None
    if re.fullmatch(r"/\d{1,2}", text):
        return int(text[1:]), None
    if re.fullmatch(r"\d{1,6}", text):
        return None, int(text)
    raise SubnetError(
        f"'{text}' isn't a split size. Use a new prefix like /26, or a number of subnets like 8."
    )


def split_network(
    network: ipaddress.IPv4Network, new_prefix: int | None = None, count: int | None = None
) -> list[ipaddress.IPv4Network]:
    """Cut a network into equal smaller subnets, by new prefix or by how many are wanted."""
    if count is not None:
        if count < 2:
            raise SubnetError("Split into at least 2 subnets.")
        # Subnets come in powers of two: 5 subnets needs 3 more prefix bits (8 subnets).
        # (count - 1).bit_length() is "how many bits to count to count - 1": 5 -> 4 -> 3 bits.
        new_prefix = network.prefixlen + (count - 1).bit_length()
        if new_prefix > 32:
            raise SubnetError(
                f"{network} can't be split into {count:,} subnets: it only has "
                f"{network.num_addresses:,} addresses."
            )
    if new_prefix is None:
        raise SubnetError("Give a new prefix (e.g. /26) or a number of subnets (e.g. 8).")
    if not network.prefixlen < new_prefix <= 32:
        raise SubnetError(
            f"To split {network}, the new prefix must be longer than /{network.prefixlen} and at most /32."
        )
    subnet_count = 2 ** (new_prefix - network.prefixlen)
    if subnet_count > MAX_SUBNETS:
        raise SubnetError(
            f"That makes {subnet_count:,} subnets; the limit is {MAX_SUBNETS:,} at a time. "
            "Split a smaller network, or into bigger subnets."
        )
    return list(network.subnets(new_prefix=new_prefix))


def _read_size(text: str) -> int:
    """Turn "22", "255.255.252.0" (mask) or "0.0.3.255" (wildcard) into a prefix length."""
    if re.fullmatch(r"\d{1,2}", text):
        prefix = int(text)
        if prefix > 32:
            raise SubnetError(f"/{prefix} is too long: an IPv4 prefix is /0 to /32.")
        return prefix
    if not _is_address(text):
        raise SubnetError(f"'{text}' isn't a prefix length, mask or wildcard.")

    value = int(ipaddress.IPv4Address(text))
    if value == 0:
        return 32  # wildcard 0.0.0.0 = exactly one host (see the module docstring)
    if _is_contiguous_mask(value):
        return value.bit_count()  # a mask's prefix = how many 1 bits it has
    inverted = value ^ 0xFFFFFFFF  # flip all 32 bits: a wildcard becomes its mask
    if _is_contiguous_mask(inverted):
        return inverted.bit_count()
    raise SubnetError(
        f"'{text}' isn't a subnet mask or wildcard: its bits aren't one solid run, so it doesn't "
        "describe a subnet."
    )


def _is_contiguous_mask(value: int) -> bool:
    """True if the 32-bit value is all 1s followed by all 0s (a valid subnet mask).

    The trick: flip the bits and add one. For a valid mask, the flipped value is all 0s then all
    1s (like 0b0011), and adding one carries into a single 1 bit (0b0100), a power of two. A power
    of two has exactly one 1 bit, which `x & (x - 1) == 0` checks.
    """
    flipped_plus_one = (value ^ 0xFFFFFFFF) + 1
    return flipped_plus_one & (flipped_plus_one - 1) == 0


def _is_address(text: str) -> bool:
    try:
        ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return True
