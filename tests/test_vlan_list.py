"""Tests for app/tools/vlan_list.py.

All VLAN lists here are invented. The space-separated, wrapped sample mimics the shape of a switch's
"show" output, not any real device's VLANs.
"""

import pytest

from app.tools.vlan_list import MAX_VLAN, VLANListError, compress, free_vlans, parse_vlans

# --- reading -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "10,20-23,100",
        "10, 20-23, 100",
        "10 20 21 22 23 100",
        "10\n20\n21\n22\n23\n100\n",
        "100,23,22\n21 20 10",  # any order
        "10,20 - 23,100",  # spaced-out range
        "10\r\n20-23\r\n100",  # Windows line endings
        "10,20-22,21-23,100,10",  # overlaps and a duplicate
    ],
)
def test_every_input_style_gives_the_same_vlans(text):
    assert parse_vlans(text).vlans == [10, 20, 21, 22, 23, 100]


def test_wrapped_space_separated_list():
    text = "2 3 4 5 6 7 8 9\n 10 11 12 40 41\n 42 300 4000"
    result = parse_vlans(text)
    assert compress(result.vlans) == "2-12,40-42,300,4000"
    assert result.invalid == []


def test_counts_items():
    assert parse_vlans("10,20-23,100").items == 3


@pytest.mark.parametrize(
    "item, reason",
    [
        ("0", "outside 1-4094"),
        ("4095", "outside 1-4094"),
        ("4000-4100", "outside 1-4094"),
        ("23-20", "runs backwards"),
        ("vlan", "not a VLAN number or range"),
        ("1/7/1", "not a VLAN number or range"),
        ("10-", "not a VLAN number or range"),
        ("abc10", "not a VLAN number or range"),
        ("10000", "outside 1-4094"),  # five digits: still read, then refused by value
        ("123456", "not a VLAN number or range"),  # six or more digits: never converted
        ("10-123456", "not a VLAN number or range"),
        ("9" * 5000, "not a VLAN number or range"),  # past int()'s 4,300-digit limit
    ],
)
def test_invalid_items_are_reported_not_dropped(item, reason):
    result = parse_vlans(f"5,{item},6")
    assert result.vlans == [5, 6]
    assert len(result.invalid) == 1
    text, why = result.invalid[0]
    assert text == item and reason in why


def test_a_pasted_table_row_reports_its_extra_columns():
    # The words and the port in front of the VLANs are listed as invalid, not read as VLANs.
    result = parse_vlans("UPLINK trunk 1/1/1,1/2/1 7 8 9")
    assert result.vlans == [7, 8, 9]
    assert [text for text, _ in result.invalid] == ["UPLINK", "trunk", "1/1/1", "1/2/1"]


def test_full_range():
    assert len(parse_vlans(f"1-{MAX_VLAN}").vlans) == MAX_VLAN


def test_empty_paste_is_refused():
    with pytest.raises(VLANListError, match="Paste some VLANs"):
        parse_vlans(" ,\n ")


# --- compress ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vlans, expected",
    [
        ([], ""),
        ([7], "7"),
        ([7, 8], "7-8"),
        ([7, 9], "7,9"),
        ([10, 20, 21, 22, 23, 100], "10,20-23,100"),
        ([1, 2, 3, 5, 6, 8], "1-3,5-6,8"),
        (list(range(1, 4095)), "1-4094"),
    ],
)
def test_compress(vlans, expected):
    assert compress(vlans) == expected


def test_round_trip():
    text = "5-40,44-45,60-63,77,150-161,2900"
    assert compress(parse_vlans(text).vlans) == text


# --- free VLANs ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vlans, expected",
    [
        ([], []),
        ([7], []),
        ([7, 8], []),
        ([7, 9], [8]),
        ([10, 20, 21, 23], [11, 12, 13, 14, 15, 16, 17, 18, 19, 22]),
    ],
)
def test_free_vlans(vlans, expected):
    assert free_vlans(vlans) == expected


def test_free_vlans_compressed():
    vlans = parse_vlans("5-40,44-45,60-63,77").vlans
    assert compress(free_vlans(vlans)) == "41-43,46-59,64-76"
