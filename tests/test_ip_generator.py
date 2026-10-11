"""Tests for app/tools/ip_generator.py.

Most tests pass a seeded random.Random so a failure can be reproduced exactly. The checks themselves
don't depend on the seed: they test properties (unique, inside the subnet, no network/broadcast)
rather than specific addresses.
"""

import ipaddress
import random

import pytest

from app.tools.ip_generator import (
    MAX_COUNT,
    IPGeneratorError,
    IPResult,
    format_ips,
    generate_ips,
    parse_target,
    prefix_for_count,
    random_private_network,
)

Net = ipaddress.IPv4Network
Addr = ipaddress.IPv4Address


def seeded() -> random.Random:
    """A random generator that gives the same sequence every run."""
    return random.Random(1234)


def assert_valid(result: IPResult, count: int) -> None:
    """The properties every result must have, whatever the input."""
    assert len(result.addresses) == count
    assert len(set(result.addresses)) == count, "addresses repeat"
    for address in result.addresses:
        assert address in result.network
        assert address != result.network.network_address
        assert address != result.network.broadcast_address


# --- parse_target --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("192.168.4.0/22", Net("192.168.4.0/22")),
        ("192.168.4.0/255.255.252.0", Net("192.168.4.0/22")),
        ("192.168.4.0 255.255.252.0", Net("192.168.4.0/22")),
        ("  192.168.4.0    255.255.252.0  ", Net("192.168.4.0/22")),
        ("192.168.5.9/22", Net("192.168.4.0/22")),  # host bits are cleared
        ("172.20.0.0", Addr("172.20.0.0")),  # bare address = starting point
    ],
)
def test_parse_target_accepts_common_forms(text, expected):
    assert parse_target(text) == expected


@pytest.mark.parametrize("text", ["", "   "])
def test_parse_target_empty_means_none(text):
    assert parse_target(text) is None


@pytest.mark.parametrize(
    "text", ["hello", "192.168.4.0/33", "300.1.1.1", "192.168.4.0/255.0.255.0", "1.2.3.4 a b"]
)
def test_parse_target_rejects_garbage_with_friendly_error(text):
    with pytest.raises(IPGeneratorError):
        parse_target(text)


# --- prefix_for_count ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "count, prefix",
    [(1, 30), (2, 30), (3, 29), (254, 24), (255, 23), (300, 23), (510, 23), (511, 22), (MAX_COUNT, 16)],
)
def test_prefix_for_count_picks_smallest_subnet(count, prefix):
    assert prefix_for_count(count) == prefix


@pytest.mark.parametrize("count", [0, -5, MAX_COUNT + 1])
def test_prefix_for_count_rejects_out_of_range(count):
    with pytest.raises(IPGeneratorError):
        prefix_for_count(count)


# --- random_private_network ----------------------------------------------------------------------


def test_random_networks_never_use_10_slash_8():
    rng = seeded()
    allowed = [Net("172.16.0.0/12"), Net("192.168.0.0/16")]
    for _ in range(500):
        network = random_private_network(24, rng)
        assert network.prefixlen == 24
        assert any(network.subnet_of(block) for block in allowed)
        assert not network.subnet_of(Net("10.0.0.0/8"))


def test_random_networks_use_both_blocks():
    rng = seeded()
    seen = {random_private_network(24, rng).network_address.packed[0] for _ in range(200)}
    assert seen == {172, 192}


# --- generate_ips: the three ways to call it -----------------------------------------------------


def test_subnet_only_fills_every_usable_address():
    result = generate_ips(target=Net("192.168.4.0/24"), rng=seeded())
    assert_valid(result, 254)
    assert set(result.addresses) == set(Net("192.168.4.0/24").hosts())


def test_subnet_only_is_shuffled():
    result = generate_ips(target=Net("192.168.4.0/24"), rng=seeded())
    assert result.addresses != sorted(result.addresses)


def test_subnet_and_count():
    result = generate_ips(count=50, target=Net("192.168.4.0/22"), rng=seeded())
    assert result.network == Net("192.168.4.0/22")
    assert_valid(result, 50)


def test_count_only_picks_sized_random_private_network():
    result = generate_ips(count=300, rng=seeded())
    assert result.network.prefixlen == 23
    assert not result.network.subnet_of(Net("10.0.0.0/8"))
    assert_valid(result, 300)


def test_count_with_starting_address_rounds_down_to_boundary():
    result = generate_ips(count=300, target=Addr("172.20.1.0"), rng=seeded())
    assert result.network == Net("172.20.0.0/23")
    assert_valid(result, 300)


def test_typed_network_outside_random_blocks_is_used_as_given():
    # Random networks only come from 172.16/12 and 192.168/16, but a network the user types is used
    # exactly as given. (A documentation range: example addresses never come from 10/8.)
    result = generate_ips(count=5, target=Net("198.51.100.0/24"), rng=seeded())
    assert result.network == Net("198.51.100.0/24")


def test_count_from_huge_network_is_fine():
    # Sampling from a /8 must not try to list 16 million addresses.
    result = generate_ips(count=1000, target=Net("172.16.0.0/12"), rng=seeded())
    assert_valid(result, 1000)


def test_maximum_count_works():
    assert_valid(generate_ips(count=MAX_COUNT, rng=seeded()), MAX_COUNT)


def test_same_seed_gives_same_result():
    assert generate_ips(count=20, rng=seeded()) == generate_ips(count=20, rng=seeded())


def test_slash_30_gives_two_addresses():
    result = generate_ips(target=Net("192.168.4.0/30"))
    assert sorted(result.addresses) == [Addr("192.168.4.1"), Addr("192.168.4.2")]


# --- generate_ips: refusals ----------------------------------------------------------------------


@pytest.mark.parametrize("network", ["192.168.4.0/31", "192.168.4.1/32"])
def test_slash_31_and_32_are_refused(network):
    with pytest.raises(IPGeneratorError, match="/31 or /32"):
        generate_ips(target=Net(network))


def test_count_larger_than_subnet_is_refused():
    with pytest.raises(IPGeneratorError, match="only has 254"):
        generate_ips(count=255, target=Net("192.168.4.0/24"))


def test_filling_subnet_bigger_than_limit_is_refused():
    with pytest.raises(IPGeneratorError, match="more than the limit"):
        generate_ips(target=Net("172.16.0.0/15"))


def test_nothing_given_is_refused():
    with pytest.raises(IPGeneratorError, match="Give a count"):
        generate_ips()


@pytest.mark.parametrize("count", [0, MAX_COUNT + 1])
def test_bad_count_with_network_is_refused(count):
    with pytest.raises(IPGeneratorError):
        generate_ips(count=count, target=Net("172.16.0.0/12"))


# --- format_ips ----------------------------------------------------------------------------------


def make_result() -> IPResult:
    return IPResult(network=Net("192.168.4.0/22"), addresses=[Addr("192.168.4.17")])


@pytest.mark.parametrize(
    "style, expected",
    [
        ("plain", "192.168.4.17"),
        ("prefix", "192.168.4.17/22"),
        ("mask", "192.168.4.17 255.255.252.0"),
    ],
)
def test_format_styles(style, expected):
    assert format_ips(make_result(), style) == [expected]


def test_unknown_style_is_refused():
    with pytest.raises(IPGeneratorError):
        format_ips(make_result(), "fancy")
