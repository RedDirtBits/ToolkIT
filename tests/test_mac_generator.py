"""Tests for app/tools/mac_generator.py.

Like the IP tests, these check rules that must always hold (unique, right bits set) rather than
specific random values, and pass a seeded random generator so failures can be reproduced.
"""

import random

import pytest

from app.tools.limits import MAX_ITEMS
from app.tools.mac_format import parse_mac
from app.tools.mac_generator import (
    MACGeneratorError,
    generate_formatted,
    generate_macs,
    is_locally_administered,
    is_multicast,
    parse_oui,
)


def seeded() -> random.Random:
    return random.Random(1234)


# --- generate_macs -------------------------------------------------------------------------------


def test_local_mode_is_locally_administered_unicast():
    macs = generate_macs(2000, "local", rng=seeded())
    assert len(set(macs)) == 2000
    for mac in macs:
        assert is_locally_administered(mac)
        assert not is_multicast(mac)
        assert 0 <= mac < 2**48
        # The human-readable rule: the second hex digit is 2, 6, a or e.
        assert f"{mac:012x}"[1] in "26ae"


def test_local_is_the_default_mode():
    assert all(is_locally_administered(m) for m in generate_macs(50, rng=seeded()))


def test_local_mode_varies_the_first_byte():
    # The 6 free bits of the first byte must actually be used, not stuck at 02.
    first_bytes = {mac >> 40 for mac in generate_macs(2000, rng=seeded())}
    assert len(first_bytes) > 30


def test_random_mode_is_unicast_and_mixes_local_and_vendor():
    macs = generate_macs(2000, "random", rng=seeded())
    assert len(set(macs)) == 2000
    assert not any(is_multicast(m) for m in macs)
    # With 2000 random MACs, both kinds of U/L bit should show up.
    assert {is_locally_administered(m) for m in macs} == {True, False}


def test_oui_mode_keeps_the_prefix():
    oui = 0x001A2B
    macs = generate_macs(1000, "oui", oui=oui, rng=seeded())
    assert len(set(macs)) == 1000
    assert all(mac >> 24 == oui for mac in macs)


def test_maximum_count_works():
    assert len(set(generate_macs(MAX_ITEMS, rng=seeded()))) == MAX_ITEMS


def test_same_seed_gives_same_result():
    assert generate_macs(20, rng=seeded()) == generate_macs(20, rng=seeded())


@pytest.mark.parametrize("count", [0, -1, MAX_ITEMS + 1])
def test_bad_counts_are_refused(count):
    with pytest.raises(MACGeneratorError):
        generate_macs(count)


def test_unknown_mode_is_refused():
    with pytest.raises(MACGeneratorError):
        generate_macs(5, "fancy")


def test_oui_mode_without_prefix_is_refused():
    with pytest.raises(MACGeneratorError, match="OUI"):
        generate_macs(5, "oui")


# --- parse_oui -----------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["00:1a:2b", "00-1A-2B", "001a2b", "001A.2B", " 00 1a 2b "])
def test_parse_oui_accepts_common_forms(text):
    assert parse_oui(text) == 0x001A2B


@pytest.mark.parametrize("text", ["", "00:1a", "00:1a:2b:3c", "zz:1a:2b"])
def test_parse_oui_rejects_bad_input(text):
    with pytest.raises(MACGeneratorError):
        parse_oui(text)


def test_parse_oui_rejects_multicast_prefix():
    with pytest.raises(MACGeneratorError, match="multicast"):
        parse_oui("01:00:5e")


# --- generate_formatted --------------------------------------------------------------------------


def test_generate_formatted_defaults_to_lowercase_colon():
    for text in generate_formatted(20, rng=seeded()):
        assert text == text.lower()
        assert len(text) == 17 and text.count(":") == 5


def test_generate_formatted_oui_dotted_upper():
    texts = generate_formatted(10, "oui", "00:1a:2b", "dotted", upper=True, rng=seeded())
    for text in texts:
        assert text.startswith("001A.2B")
        assert parse_mac(text) >> 24 == 0x001A2B


def test_generate_formatted_ignores_oui_text_in_other_modes():
    # A leftover value in the OUI box shouldn't matter unless "oui" mode is chosen.
    assert len(generate_formatted(5, "local", "garbage", rng=seeded())) == 5
