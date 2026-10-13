"""Tests for app/tools/oui_data.py.

They use the small fake registry files in tests/fixtures/ieee/ (same layout as IEEE's, invented
vendors), never the real downloaded list.
"""

from pathlib import Path

import pytest

from app.tools.oui_data import (
    KIND_LABELS,
    OUIDataError,
    load_folder,
    lookup_lines,
    lookup_text,
    parse_registry_csv,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ieee"
HEADER = "Registry,Assignment,Organization Name,Organization Address\n"


@pytest.fixture(scope="module")
def db():
    return load_folder(FIXTURES)


# --- reading the files ---------------------------------------------------------------------------


def test_load_folder_reads_all_three_files(db):
    assert db.counts() == {"MA-S": 1, "MA-M": 2, "MA-L": 8}  # 9 rows, one prefix listed twice
    assert len(db) == 11


def test_load_folder_with_no_files_gives_none(tmp_path):
    assert load_folder(tmp_path) is None


def test_load_folder_with_only_some_files(tmp_path):
    (tmp_path / "mam.csv").write_text((FIXTURES / "mam.csv").read_text())
    database = load_folder(tmp_path)
    assert database is not None  # load_folder gives None only when no file is there at all
    assert database.counts() == {"MA-S": 0, "MA-M": 2, "MA-L": 0}


def test_parse_detects_the_block():
    block, entries = parse_registry_csv(HEADER + "MA-S,BC567801A,Tiny,addr\n")
    assert block == "MA-S" and entries[0].prefix == "BC567801A"


def test_parse_accepts_a_bom_and_crlf():
    block, entries = parse_registry_csv("﻿" + HEADER.replace("\n", "\r\n") + "MA-L,001a2b,X,\r\n")
    assert block == "MA-L" and entries[0].prefix == "001A2B"


@pytest.mark.parametrize(
    "text, message",
    [
        ("hello,world\n1,2\n", "isn't an IEEE registry CSV"),
        ("", "isn't an IEEE registry CSV"),
        (HEADER, "no entries"),
        (HEADER + "MA-X,001A2B,X,\n", "Unknown registry"),
        (HEADER + "MA-L,001A2B,X,\nMA-M,001A2B3,Y,\n", "mixes registries"),
        (HEADER + "MA-L,001A2,X,\n", "isn't a 6-digit MA-L prefix"),
        (HEADER + "MA-L\n", "too few columns"),
        # A quote that's never closed: the csv module's own error, reported like the others.
        (HEADER + 'MA-L,001A2B,"' + "x" * 200_000, "isn't a readable CSV"),
    ],
)
def test_parse_refuses_files_that_are_not_registries(text, message):
    with pytest.raises(OUIDataError, match=message):
        parse_registry_csv(text)


# --- lookups -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["00:1a:2b:3c:4d:5e", "00-1A-2B-3C-4D-5E", "001a.2b3c.4d5e", "001a2b3c4d5e", "00:1a:2b", "001A2B"],
)
def test_lookup_any_format_and_bare_prefix(db, text):
    result = lookup_text(text, db)
    assert result.kind == "vendor"
    assert result.label == "Example Networks, Inc."


def test_longest_prefix_wins(db):
    # AC1234 is IEEE's own block; AC12345 inside it is a medium block with a real owner.
    assert lookup_text("ac:12:34:5f:00:01", db).label == "Medium Block Devices"
    assert lookup_text("bc:56:78:01:af:ff", db).label == "Tiny Sensors GmbH"


def test_split_block_without_a_sub_assignment_shows_ieee(db):
    result = lookup_text("ac:12:34:c0:00:01", db)
    assert result.label == "IEEE Registration Authority"


def test_bare_prefix_of_a_split_block_asks_for_the_full_mac(db):
    result = lookup_text("ac:12:34", db)
    assert "give the full MAC" in result.label


def test_private_entries(db):
    assert lookup_text("0c:0c:0c:00:00:01", db).kind == "private"
    assert lookup_text("ac:12:34:a0:00:01", db).kind == "private"  # a private MA-M block
    assert lookup_text("0c0c0c", db).label == KIND_LABELS["private"]


def test_local_and_multicast_are_recognised_before_the_list(db):
    assert lookup_text("02:1a:2b:3c:4d:5e", db).kind == "local"
    assert lookup_text("01:00:5e:00:00:01", db).kind == "multicast"
    assert lookup_text("ff:ff:ff:ff:ff:ff", db).kind == "multicast"


def test_unknown_and_invalid(db):
    assert lookup_text("00:99:99:00:00:01", db).kind == "unknown"
    for text in ("hello", "00:1a", "00:1a:2b:3c:4d:5e:6f", "zz:1a:2b"):
        assert lookup_text(text, db).kind == "invalid"


def test_prefix_with_several_owners_shows_all(db):
    assert lookup_text("08:00:30:12:34:56", db).label == "Old Research Corp / Other Institute"


def test_lookup_lines_keeps_blank_lines(db):
    results = lookup_lines("00:1a:2b:00:00:01\n\nnonsense\n", db)
    assert [r.kind if r else None for r in results] == ["vendor", None, "invalid"]


# --- reverse search ------------------------------------------------------------------------------


def test_search_ignores_case_and_sorts(db):
    found = db.search("example networks")
    assert [e.vendor for e in found] == ["Example Networks Labs", "Example Networks, Inc."]


def test_search_matches_accented_names(db):
    assert [e.prefix for e in db.search("équipements")] == ["F0A1B2"]


def test_search_finds_every_block_size(db):
    assert [e.block for e in db.search("tiny sensors")] == ["MA-S"]


def test_search_needs_two_characters(db):
    with pytest.raises(OUIDataError, match="at least 2"):
        db.search(" x ")


def test_search_with_no_match(db):
    assert db.search("no such vendor") == []


# --- prefix formatting ---------------------------------------------------------------------------


def test_format_large_block_prefix(db):
    (entry,) = db.search("Example Networks, Inc.")
    assert entry.format_prefix() == "00:1a:2b"
    assert entry.format_prefix("hyphen", upper=True) == "00-1A-2B"
    assert entry.format_prefix("dotted") == "001a.2b"


def test_format_medium_and_small_block_prefix(db):
    (medium,) = db.search("Medium Block")
    (small,) = db.search("Tiny Sensors")
    assert medium.format_prefix() == "ac:12:34:50:00:00/28"
    assert small.format_prefix("dotted") == "bc56.7801.a000/36"
