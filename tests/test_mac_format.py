"""Tests for app/tools/mac_format.py. All MACs here are made up."""

import pytest

from app.tools.mac_format import MACError, convert_lines, format_mac, parse_mac

# One made-up MAC as an integer, used throughout.
VALUE = 0x021A2B3C4D5E


# --- parse_mac -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "02:1a:2b:3c:4d:5e",
        "02-1A-2B-3C-4D-5E",
        "021a.2b3c.4d5e",
        "021A2B3C4D5E",
        "  02:1a:2b:3c:4d:5e  ",  # surrounding spaces are fine
        "02:1A:2b:3C:4d:5E",  # mixed case is fine
    ],
)
def test_parse_accepts_all_input_forms(text):
    assert parse_mac(text) == VALUE


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "02:1a:2b:3c:4d",  # too short
        "02:1a:2b:3c:4d:5e:6f",  # too long
        "02:1a-2b:3c:4d:5e",  # mixed separators
        "02:1a:2b:3c:4d:5g",  # g isn't hex
        "021a.2b3c-4d5e",  # mixed dotted/hyphen
        "2:1a:2b:3c:4d:5e",  # a one-digit group
        "021a2b3c4d5",  # 11 digits
    ],
)
def test_parse_rejects_non_macs(text):
    with pytest.raises(MACError):
        parse_mac(text)


# --- format_mac ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "style, upper, expected",
    [
        ("colon", False, "02:1a:2b:3c:4d:5e"),
        ("hyphen", False, "02-1a-2b-3c-4d-5e"),
        ("dotted", False, "021a.2b3c.4d5e"),
        ("colon", True, "02:1A:2B:3C:4D:5E"),
        ("hyphen", True, "02-1A-2B-3C-4D-5E"),
        ("dotted", True, "021A.2B3C.4D5E"),
    ],
)
def test_format_styles_and_case(style, upper, expected):
    assert format_mac(VALUE, style, upper) == expected


def test_format_defaults_to_lowercase_colon():
    assert format_mac(VALUE) == "02:1a:2b:3c:4d:5e"


def test_format_pads_leading_zeros():
    assert format_mac(0x000000000001) == "00:00:00:00:00:01"


def test_format_rejects_unknown_style():
    with pytest.raises(MACError):
        format_mac(VALUE, "bare")


@pytest.mark.parametrize("value", [-1, 2**48])
def test_format_rejects_out_of_range(value):
    with pytest.raises(MACError):
        format_mac(value)


@pytest.mark.parametrize("style", ["colon", "hyphen", "dotted"])
def test_round_trip(style):
    assert parse_mac(format_mac(VALUE, style)) == VALUE


# --- convert_lines -------------------------------------------------------------------------------


def test_convert_block_skips_blanks_and_reports_bad_lines():
    pasted = "02:1a:2b:3c:4d:5e\n\n021a.2b3c.4d5f\nnot a mac\r\n  02-1A-2B-3C-4D-60  \n"
    result = convert_lines(pasted, "hyphen")
    assert result.converted == ["02-1a-2b-3c-4d-5e", "02-1a-2b-3c-4d-5f", "02-1a-2b-3c-4d-60"]
    assert result.errors == [(4, "not a mac")]


def test_convert_uppercase_dotted():
    result = convert_lines("02:1a:2b:3c:4d:5e", "dotted", upper=True)
    assert result.converted == ["021A.2B3C.4D5E"]


def test_convert_empty_input():
    result = convert_lines("   \n\n")
    assert result.converted == [] and result.errors == []


def test_convert_bad_style_is_one_error():
    with pytest.raises(MACError):
        convert_lines("02:1a:2b:3c:4d:5e\n02:1a:2b:3c:4d:5f", "bare")
