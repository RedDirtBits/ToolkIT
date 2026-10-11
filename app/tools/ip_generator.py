"""Random IPv4 address generator.

Three ways to ask for addresses:

1. A subnet only ("192.168.4.0/22")      -> every usable address in it, in random order.
2. A subnet and a count                    -> that many random addresses from the subnet.
3. A count only (300)                      -> the smallest subnet that holds 300 (/23), placed in a
                                              random private block, filled with 300 random addresses.
   A count plus a bare starting address   -> the same, but the subnet is built around that address
   ("172.20.0.0" + 300)                       (172.20.0.0/23) instead of a random block.

Rules that apply everywhere:
- Never return the network or broadcast address, and never repeat an address.
- /31 and /32 are refused (they have no "usable hosts" in the normal sense).
- At most MAX_COUNT addresses per request (one full /16), so a typo can't hang the app.
- Random blocks come from 172.16.0.0/12 and 192.168.0.0/16 only. 10.0.0.0/8 is deliberately left
  out: it's the most widely used internal range, so fakes from it could pass for real addresses.
  (A network the user types in explicitly is used as given, even if it's in 10/8.)

This module is pure Python with no web code, so it can be tested on its own.
"""

from __future__ import annotations

import ipaddress
import random
from dataclasses import dataclass

# The most addresses one request may produce: the usable hosts of a /16 (65,536 - 2).
MAX_COUNT = 65_534

# The smallest and largest prefixes we'll build or fill.
# /16 is the biggest subnet whose usable hosts fit within MAX_COUNT; /30 is the smallest subnet that
# still has a network and broadcast address to skip (2 usable hosts).
MIN_PREFIX = 16
MAX_PREFIX = 30

# Where random networks come from. 10.0.0.0/8 is intentionally missing (see the module docstring).
RANDOM_PARENT_BLOCKS = (
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)

# How each address can be written out. The keys are what the web form sends.
OUTPUT_STYLES = ("plain", "prefix", "mask")


class IPGeneratorError(ValueError):
    """A request we can't fulfil. The message is written for the user and is safe to show as-is."""


@dataclass(frozen=True)
class IPResult:
    """What a generation request produced.

    `network` is kept alongside the addresses so the page can show which subnet was used (handy when
    it was picked at random) and so addresses can be written with their prefix or mask.
    """

    network: ipaddress.IPv4Network
    addresses: list[ipaddress.IPv4Address]


def parse_target(text: str) -> ipaddress.IPv4Network | ipaddress.IPv4Address | None:
    """Turn what the user typed in the "network" box into a network, a starting address, or nothing.

    Accepted forms:
        ""                              -> None (no network given)
        "192.168.4.0/22"                -> network
        "192.168.4.0/255.255.252.0"     -> network (mask instead of prefix length)
        "192.168.4.0 255.255.252.0"     -> network (space instead of slash, as in Cisco configs)
        "172.20.0.0"                    -> starting address (the subnet size comes from the count)

    Host bits are allowed and cleared: "192.168.5.9/22" means 192.168.4.0/22. That's what an engineer
    pasting an interface address usually means.
    """
    text = text.strip()
    if not text:
        return None

    # "address mask" with any amount of whitespace between -> "address/mask".
    # split() with no argument splits on runs of whitespace, so "a   b" gives ["a", "b"].
    parts = text.split()
    if len(parts) == 2:
        text = f"{parts[0]}/{parts[1]}"
    elif len(parts) > 2:
        raise IPGeneratorError(f"'{text}' isn't a network. Use e.g. 192.168.4.0/22.")

    try:
        if "/" in text:
            # strict=False clears host bits instead of raising an error (see the docstring).
            return ipaddress.IPv4Network(text, strict=False)
        return ipaddress.IPv4Address(text)
    except ValueError:
        # ipaddress's own messages are fine for programmers but not friendly; replace them.
        raise IPGeneratorError(
            f"'{text}' isn't a valid IPv4 network or address. Use e.g. 192.168.4.0/22, "
            "192.168.4.0 255.255.252.0 or 172.20.0.0."
        ) from None


def prefix_for_count(count: int) -> int:
    """Return the smallest subnet (longest prefix) whose usable hosts hold `count` addresses.

    Example: 300 -> 23, because a /24 has 254 usable hosts (too few) and a /23 has 510.
    """
    _check_count(count)
    # Walk from small subnets (/30) to big ones (/16) and stop at the first that's big enough.
    for prefix in range(MAX_PREFIX, MIN_PREFIX - 1, -1):
        if _usable_hosts(prefix) >= count:
            return prefix
    # Unreachable while MAX_COUNT equals the usable hosts of a /MIN_PREFIX, but fail loudly if those
    # two constants are ever changed out of step.
    raise IPGeneratorError(f"No subnet of /{MIN_PREFIX} or smaller holds {count:,} addresses.")


def random_private_network(prefix: int, rng: random.Random) -> ipaddress.IPv4Network:
    """Pick a random subnet of the given size inside one of RANDOM_PARENT_BLOCKS.

    Think of 192.168.0.0/16 as a street of 256 houses when cutting it into /24s: we pick a random
    house number and work out its address, rather than listing all the houses first.
    """
    parent = rng.choice(RANDOM_PARENT_BLOCKS)
    # How many subnets of this size fit in the parent, e.g. a /16 holds 2**(24-16) = 256 /24s.
    subnet_count = 2 ** (prefix - parent.prefixlen)
    subnet_size = 2 ** (32 - prefix)  # addresses per subnet, e.g. 256 for a /24
    index = rng.randrange(subnet_count)
    # IPv4Address supports "+ integer", which moves that many addresses forward.
    start = parent.network_address + index * subnet_size
    return ipaddress.IPv4Network((start, prefix))


def generate_ips(
    count: int | None = None,
    target: ipaddress.IPv4Network | ipaddress.IPv4Address | None = None,
    rng: random.Random | None = None,
) -> IPResult:
    """Generate unique random IPv4 addresses. See the module docstring for the three ways to call it.

    `target` is what parse_target() returned. `rng` lets tests pass a seeded random generator so
    results are repeatable; normal use leaves it out and gets a fresh one.
    """
    rng = rng or random.Random()

    if isinstance(target, ipaddress.IPv4Network):
        network = target
        if network.prefixlen > MAX_PREFIX:
            raise IPGeneratorError(
                f"/{network.prefixlen} networks are refused: a /31 or /32 has no usable host "
                "addresses to generate. Use /30 or larger."
            )
        usable = network.num_addresses - 2
        if count is None:
            # Subnet only: fill it completely.
            if usable > MAX_COUNT:
                raise IPGeneratorError(
                    f"{network} has {usable:,} usable addresses, more than the limit of "
                    f"{MAX_COUNT:,}. Give a count, or use a /{MIN_PREFIX} or smaller."
                )
            count = usable
        else:
            _check_count(count)
            if count > usable:
                raise IPGeneratorError(
                    f"{network} only has {usable:,} usable addresses, so it can't hold {count:,}."
                )
    else:
        # No network given (or only a starting address): the count decides the subnet size.
        if count is None:
            raise IPGeneratorError("Give a count, a network, or both.")
        prefix = prefix_for_count(count)
        if isinstance(target, ipaddress.IPv4Address):
            # strict=False rounds the address down to the subnet boundary,
            # e.g. 172.20.1.0 with /23 -> 172.20.0.0/23.
            network = ipaddress.IPv4Network((target, prefix), strict=False)
        else:
            network = random_private_network(prefix, rng)

    # Pick `count` different offsets from the network address. Offset 0 is the network address and
    # the last offset is the broadcast, so the range runs from 1 to num_addresses - 2.
    # rng.sample() never repeats a value, and it works on a range() without building a huge list,
    # so even a /8 is cheap.
    offsets = rng.sample(range(1, network.num_addresses - 1), count)
    addresses = [network.network_address + offset for offset in offsets]
    return IPResult(network=network, addresses=addresses)


def format_ips(result: IPResult, style: str = "plain") -> list[str]:
    """Write each address as text in the chosen style.

        plain   192.168.4.17
        prefix  192.168.4.17/22
        mask    192.168.4.17 255.255.252.0
    """
    if style not in OUTPUT_STYLES:
        choices = ", ".join(OUTPUT_STYLES)
        raise IPGeneratorError(f"Unknown output style '{style}'. Choose one of: {choices}.")
    network = result.network
    if style == "prefix":
        return [f"{address}/{network.prefixlen}" for address in result.addresses]
    if style == "mask":
        return [f"{address} {network.netmask}" for address in result.addresses]
    return [str(address) for address in result.addresses]


def _usable_hosts(prefix: int) -> int:
    """Usable host addresses in a subnet of this prefix: all addresses minus network and broadcast."""
    return 2 ** (32 - prefix) - 2


def _check_count(count: int) -> None:
    """Refuse counts below 1 or above MAX_COUNT with a message the user can act on."""
    if count < 1:
        raise IPGeneratorError("The count must be at least 1.")
    if count > MAX_COUNT:
        raise IPGeneratorError(f"The count can be at most {MAX_COUNT:,} (one full /{MIN_PREFIX}).")
