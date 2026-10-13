"""Random MAC address generator.

Three modes:

    local   (default) Locally administered unicast: the second hex digit is 2, 6, A or E
            (x2:xx:..., x6:..., xA:..., xE:...). Real vendor addresses never look like this, so
            these are safe fakes that can't clash with a real device.
    random  Any unicast MAC. May look like (or be) a real vendor's address.
    oui     A given vendor prefix (first 3 bytes, e.g. 00:1a:2b) plus 3 random bytes.

All modes keep the multicast bit at 0: a MAC with that bit set is a group address, which a real
network card never uses as its own address.

The two special bits live in the FIRST byte:

    first byte, in bits:  x x x x x x L M
                                      | +- M: 1 = multicast (group), 0 = unicast   -> always 0
                                      +--- L: 1 = locally administered, 0 = vendor -> 1 in "local"

Pure Python, no web code. Results are returned as integers; mac_format.format_mac() writes them out.
"""

from __future__ import annotations

import random
import re

from app.tools.limits import MAX_ITEMS
from app.tools.mac_format import format_mac

# The keys the web form sends.
MODES = ("local", "random", "oui")

# Bit masks for the two special bits, as they sit in the whole 48-bit number. The first byte is the
# top 8 of the 48 bits, so its bits start at position 40.
_MULTICAST_BIT = 1 << 40  # M in the docstring diagram
_LOCAL_BIT = 1 << 41  # L in the docstring diagram

_LOW_40_BITS = (1 << 40) - 1  # the five bytes after the first one


class MACGeneratorError(ValueError):
    """A request we can't fulfil. The message is written for the user and is safe to show as-is."""


def parse_oui(text: str) -> int:
    """Read a vendor prefix (first 3 bytes) like 00:1A:2B, 00-1a-2b or 001a2b; return a 24-bit int."""
    digits = re.sub(r"[:.\-\s]", "", text)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", digits):
        raise MACGeneratorError(
            f"'{text.strip()}' isn't an OUI prefix. Use the first 3 bytes, e.g. 00:1a:2b."
        )
    oui = int(digits, 16)
    # The multicast bit is the lowest bit of the first byte, i.e. bit 16 of the 24-bit prefix.
    if oui & (1 << 16):
        raise MACGeneratorError(
            f"'{text.strip()}' is a multicast prefix (its first byte is odd), so it can't be used "
            "for device addresses."
        )
    return oui


def generate_macs(
    count: int,
    mode: str = "local",
    oui: int | None = None,
    rng: random.Random | None = None,
) -> list[int]:
    """Generate `count` unique random MACs as 48-bit integers.

    How uniqueness works: each mode has a fixed number of "free" bits (46 for local, 47 for random,
    24 for oui). We draw `count` different numbers that fit in those free bits with rng.sample(), then
    place the bits around the fixed ones. Different numbers in -> different MACs out, guaranteed.
    """
    rng = rng or random.Random()

    if mode not in MODES:
        raise MACGeneratorError(f"Unknown mode '{mode}'. Choose one of: {', '.join(MODES)}.")
    if count < 1:
        raise MACGeneratorError("The count must be at least 1.")
    if count > MAX_ITEMS:
        raise MACGeneratorError(f"The count can be at most {MAX_ITEMS:,}.")

    if mode == "oui":
        if oui is None:
            raise MACGeneratorError("Give an OUI prefix (e.g. 00:1a:2b) for this mode.")
        # Free bits: the last 3 bytes (24 bits). The prefix goes in the top 24.
        return [(oui << 24) | n for n in rng.sample(range(2**24), count)]

    if mode == "local":
        # Free bits: 6 in the first byte (above L and M) + the 40 bits of the other five bytes.
        # Shift the top 6 free bits up past L and M, then set L. M stays 0.
        return [((n >> 40) << 42) | _LOCAL_BIT | (n & _LOW_40_BITS) for n in rng.sample(range(2**46), count)]

    # mode == "random": free bits: 7 in the first byte (everything but M) + 40 others.
    # Shift the top 7 free bits up past M, leaving M at 0.
    return [((n >> 40) << 41) | (n & _LOW_40_BITS) for n in rng.sample(range(2**47), count)]


def generate_formatted(
    count: int,
    mode: str = "local",
    oui_text: str = "",
    style: str = "colon",
    upper: bool = False,
    rng: random.Random | None = None,
) -> list[str]:
    """Convenience for the web page: take form values, return ready-to-show MAC strings."""
    oui = parse_oui(oui_text) if mode == "oui" else None
    return [format_mac(mac, style, upper) for mac in generate_macs(count, mode, oui, rng)]


def is_multicast(mac: int) -> bool:
    """True if the MAC's multicast (group) bit is set."""
    return bool(mac & _MULTICAST_BIT)


def is_locally_administered(mac: int) -> bool:
    """True if the MAC's locally-administered bit is set."""
    return bool(mac & _LOCAL_BIT)
