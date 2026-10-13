"""Tests for app/tools/subnet_calc.py.

Example addresses come from 172.16/12, 192.168/16 and the documentation ranges only.
"""

import ipaddress

import pytest

from app.tools.subnet_calc import (
    MAX_SUBNETS,
    SubnetError,
    address_type,
    calculate,
    parse_input,
    parse_split,
    read_as_single_host,
    split_network,
)

net = ipaddress.IPv4Network
addr = ipaddress.IPv4Address


# --- reading the input ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "192.168.4.17/22",
        "192.168.4.17/255.255.252.0",
        "192.168.4.17 255.255.252.0",
        "192.168.4.17   255.255.252.0",
        "192.168.4.17 / 22",
        "192.168.4.17 0.0.3.255",  # wildcard, as in an ACL
        "  192.168.4.17/22  ",
    ],
)
def test_every_input_form_means_the_same(text):
    interface = parse_input(text)
    assert interface.ip == addr("192.168.4.17")
    assert interface.network == net("192.168.4.0/22")


def test_single_host_forms():
    assert parse_input("192.0.2.5 0.0.0.0").network == net("192.0.2.5/32")  # ACL "host"
    assert parse_input("192.0.2.5 255.255.255.255").network == net("192.0.2.5/32")
    assert parse_input("192.0.2.5/32").network == net("192.0.2.5/32")


def test_slash_zero():
    assert parse_input("198.51.100.1/0").network == net("0.0.0.0/0")


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "Type an address"),
        ("192.168.4.17", "has no prefix or mask"),
        ("hello", "isn't an IPv4 address"),
        ("192.168.4.300/24", "isn't an IPv4 address"),
        ("192.168.4.17/33", "too long"),
        ("192.168.4.17 255.0.255.0", "bits aren't one solid run"),
        ("192.168.4.17 0.0.255.0", "bits aren't one solid run"),
        ("192.168.4.17/abc", "isn't a prefix length, mask or wildcard"),
    ],
)
def test_bad_input_is_explained(text, message):
    with pytest.raises(SubnetError, match=message):
        parse_input(text)


# --- calculate -----------------------------------------------------------------------------------


def test_normal_subnet():
    info = calculate("192.168.4.17/22")
    assert info.address == addr("192.168.4.17")
    assert info.network == net("192.168.4.0/22")
    assert info.broadcast == addr("192.168.7.255")
    assert (info.first_usable, info.last_usable) == (addr("192.168.4.1"), addr("192.168.7.254"))
    assert info.usable_hosts == 1022
    assert info.total_addresses == 1024
    assert info.netmask == addr("255.255.252.0")
    assert info.wildcard == addr("0.0.3.255")
    assert info.prefix == 22
    assert info.address_type == "Private (RFC 1918)"


def test_slash_30():
    info = calculate("203.0.113.9/30")
    assert info.network == net("203.0.113.8/30")
    assert (info.first_usable, info.last_usable) == (addr("203.0.113.9"), addr("203.0.113.10"))
    assert info.broadcast == addr("203.0.113.11")
    assert info.usable_hosts == 2


def test_slash_31_is_point_to_point():
    info = calculate("198.51.100.7/31")
    assert info.broadcast is None
    assert (info.first_usable, info.last_usable) == (addr("198.51.100.6"), addr("198.51.100.7"))
    assert info.usable_hosts == 2


def test_slash_32_is_one_host():
    info = calculate("198.51.100.7/32")
    assert info.broadcast is None
    assert info.first_usable == info.last_usable == addr("198.51.100.7")
    assert info.usable_hosts == 1
    assert info.wildcard == addr("0.0.0.0")


# --- address types -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address, expected",
    [
        ("172.16.0.1", "Private"),
        ("172.31.255.254", "Private"),
        ("192.168.1.1", "Private"),
        ("172.32.0.1", "Public"),  # just past 172.16/12
        ("100.64.0.1", "CGNAT"),
        ("192.0.2.10", "Documentation"),
        ("198.51.100.10", "Documentation"),
        ("203.0.113.10", "Documentation"),
        ("127.0.0.1", "Loopback"),
        ("169.254.10.20", "Link-local"),
        ("224.0.0.5", "Multicast"),
        ("255.255.255.255", "Limited broadcast"),
        ("240.0.0.1", "Reserved"),
        ("0.1.2.3", "This network"),
        ("198.18.0.1", "Benchmarking"),
        ("8.8.8.8", "Public"),
    ],
)
def test_address_types(address, expected):
    assert expected in address_type(addr(address))


# --- splitting -----------------------------------------------------------------------------------


def test_parse_split():
    assert parse_split("/26") == (26, None)
    assert parse_split(" / 26 ") == (26, None)
    assert parse_split("8") == (None, 8)
    assert parse_split("") == (None, None)
    with pytest.raises(SubnetError, match="isn't a split size"):
        parse_split("26x")


def test_split_by_prefix():
    subnets = split_network(net("192.168.4.0/22"), new_prefix=24)
    assert subnets == [net(f"192.168.{n}.0/24") for n in range(4, 8)]


def test_split_by_count_rounds_up_to_a_power_of_two():
    assert len(split_network(net("192.168.4.0/24"), count=8)) == 8
    subnets = split_network(net("192.168.4.0/24"), count=5)  # 5 -> 8 subnets of /27
    assert len(subnets) == 8 and subnets[0] == net("192.168.4.0/27")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"new_prefix": 24}, "must be longer than /24"),
        ({"new_prefix": 22}, "must be longer than /24"),
        ({"new_prefix": 33}, "at most /32"),
        ({"count": 1}, "at least 2"),
        ({"count": 300}, "only has 256 addresses"),
        ({}, "Give a new prefix"),
    ],
)
def test_split_errors(kwargs, message):
    with pytest.raises(SubnetError, match=message):
        split_network(net("192.168.4.0/24"), **kwargs)


def test_split_limit():
    # A /15 into /32s would be 131,072 subnets.
    with pytest.raises(SubnetError, match="the limit is"):
        split_network(net("172.16.0.0/15"), new_prefix=32)
    assert len(split_network(net("172.16.0.0/16"), new_prefix=32)) == MAX_SUBNETS


# --- the two ambiguous sizes (0.0.0.0 / 255.255.255.255) -----------------------------------------


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("192.0.2.5 0.0.0.0", "0.0.0.0"),  # ACL wildcard for one host
        ("192.0.2.5/255.255.255.255", "255.255.255.255"),  # mask for one host
        ("  0.0.0.0 255.255.255.255 ", "255.255.255.255"),  # ACL "any", read as one host
    ],
)
def test_read_as_single_host_names_the_ambiguous_size(text, size):
    assert read_as_single_host(text) == size
    assert calculate(text).prefix == 32  # still read as one host, as before


@pytest.mark.parametrize("text", ["192.0.2.5/32", "192.0.2.5 255.255.255.0", "0.0.0.0/0", "192.0.2.5"])
def test_read_as_single_host_is_none_for_clear_sizes(text):
    # /32 typed as a prefix isn't ambiguous; neither is anything else (or no size at all).
    assert read_as_single_host(text) is None
