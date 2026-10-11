"""Tests for app/tools/ip_list.py.

Example addresses come from 172.16/12, 192.168/16 and the documentation ranges only.
"""

import ipaddress

import pytest

from app.tools.ip_list import (
    MAX_LINES,
    IPListError,
    clean_up,
    covering_block,
    format_block,
    format_item,
    parse_item,
)

net = ipaddress.IPv4Network


# --- reading one line ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("192.168.4.17", "192.168.4.17/32"),
        ("  192.168.4.17  ", "192.168.4.17/32"),
        ("192.168.4.0/24", "192.168.4.0/24"),
        ("192.168.4.0 255.255.255.0", "192.168.4.0/24"),
        ("192.168.4.0/255.255.255.0", "192.168.4.0/24"),
        ("192.168.4.0 0.0.0.255", "192.168.4.0/24"),  # ACL wildcard
        ("192.168.4.17/24", "192.168.4.17/32"),  # host bits: interface notation, the address
        ("192.168.4.17 255.255.255.0", "192.168.4.17/32"),
        ("192.168.4.17 0.0.0.0", "192.168.4.17/32"),  # ACL "host"
    ],
)
def test_parse_item(text, expected):
    assert parse_item(text) == net(expected)


@pytest.mark.parametrize("text", ["hello", "192.168.4", "192.168.4.300", "192.168.4.0/33", "192.168.4.0 255.0.255.0"])
def test_parse_item_refuses_non_addresses(text):
    with pytest.raises(IPListError):
        parse_item(text)


# --- clean_up ------------------------------------------------------------------------------------


def test_sorts_numerically_not_as_text():
    result = clean_up("192.168.4.10\n192.168.4.2\n192.168.4.100\n172.16.0.1")
    assert [format_item(n) for n in result.sorted] == [
        "172.16.0.1", "192.168.4.2", "192.168.4.10", "192.168.4.100",
    ]


def test_deduplicates_and_keeps_original_order():
    result = clean_up("192.0.2.9\n192.0.2.1\n192.0.2.9\n192.0.2.1/32\n192.0.2.5")
    assert [format_item(n) for n in result.original] == ["192.0.2.9", "192.0.2.1", "192.0.2.5"]
    assert result.duplicates == 2


def test_counts_blank_and_invalid_lines():
    result = clean_up("192.0.2.1\n\n   \nnot an ip\n192.0.2.1\n192.0.2.999\n")
    assert result.total == 4  # blank lines aren't counted
    assert result.invalid == [(4, "not an ip"), (6, "192.0.2.999")]
    assert result.duplicates == 1
    assert len(result.original) == 1


def test_summarizes_exactly():
    # .0-.3 make a /30, .4-.7 another; together a /29. .9 stays alone.
    text = "\n".join(f"192.0.2.{n}" for n in (3, 0, 1, 2, 4, 5, 6, 7, 9))
    result = clean_up(text)
    assert result.summary == [net("192.0.2.0/29"), net("192.0.2.9/32")]


def test_summary_merges_networks_and_contained_addresses():
    result = clean_up("192.168.4.0/24\n192.168.5.0/24\n192.168.4.77\n192.168.6.0/23")
    assert result.summary == [net("192.168.4.0/22")]


def test_summary_never_adds_addresses():
    # .1 and .2 can't be one block without also including .0 or .3.
    result = clean_up("198.51.100.1\n198.51.100.2")
    assert result.summary == [net("198.51.100.1/32"), net("198.51.100.2/32")]


def test_covering_block_and_extra_addresses():
    result = clean_up("198.51.100.1\n198.51.100.2")
    assert result.covering == net("198.51.100.0/30")
    assert result.extra == 2  # .0 and .3


def test_covering_block_for_one_item():
    assert covering_block([net("192.168.4.0/24")]) == net("192.168.4.0/24")


def test_covering_block_across_far_apart_addresses():
    assert covering_block([net("172.16.0.1/32"), net("172.31.255.254/32")]) == net("172.16.0.0/12")


def test_only_invalid_lines():
    result = clean_up("junk\nmore junk")
    assert result.original == [] and result.summary == [] and result.covering is None
    assert len(result.invalid) == 2


def test_empty_paste_is_refused():
    with pytest.raises(IPListError, match="at least one"):
        clean_up(" \n\n")


def test_too_many_lines_is_refused():
    with pytest.raises(IPListError, match="at most"):
        clean_up("192.0.2.1\n" * (MAX_LINES + 1))


def test_a_full_slash_16_summarizes_to_one_block():
    text = "\n".join(str(ipaddress.IPv4Address(int(ipaddress.IPv4Address("172.20.0.0")) + n)) for n in range(65_534))
    result = clean_up(text)
    # 65,534 of the 65,536 addresses (no .255.254/.255.255): fewest exact blocks.
    assert result.covering == net("172.20.0.0/16")
    assert result.extra == 2
    assert len(result.summary) == 15


# --- formatting ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "style, expected",
    [
        ("prefix", "192.168.4.0/22"),
        ("mask", "192.168.4.0 255.255.252.0"),
        ("wildcard", "192.168.4.0 0.0.3.255"),
    ],
)
def test_format_block(style, expected):
    assert format_block(net("192.168.4.0/22"), style) == expected


def test_format_block_single_host():
    assert format_block(net("192.0.2.5/32"), "prefix") == "192.0.2.5/32"
    assert format_block(net("192.0.2.5/32"), "wildcard") == "192.0.2.5 0.0.0.0"


def test_format_block_unknown_style():
    with pytest.raises(IPListError, match="Unknown style"):
        format_block(net("192.0.2.0/24"), "binary")


def test_format_item():
    assert format_item(net("192.0.2.5/32")) == "192.0.2.5"
    assert format_item(net("192.0.2.0/24")) == "192.0.2.0/24"
