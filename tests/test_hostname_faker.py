"""Tests for app/tools/hostname_faker.py.

All hostnames here are invented. Like the other tool tests, these check rules that must always hold
(same shape, kept pieces kept, no repeats, no real names leaking) rather than specific random
values, and pass a seeded random generator so failures can be reproduced.
"""

import random
import string

import pytest

from app.tools.hostname_faker import (
    MAX_LINES,
    HostnameFakerError,
    fake_hostnames,
    parse_keep_words,
    split_pieces,
)


def seeded() -> random.Random:
    return random.Random(1234)


def shape(hostname: str) -> str:
    """Reduce a hostname to its shape: a = letter, 9 = digit, separators as-is."""
    return "".join(
        "a" if c in string.ascii_letters else "9" if c in string.digits else c for c in hostname
    )


# --- split_pieces --------------------------------------------------------------------------------


def test_split_at_separators_and_letter_digit_changes():
    assert split_pieces("exsite-wing-bld01a-cor-01") == [
        "exsite", "-", "wing", "-", "bld", "01", "a", "-", "cor", "-", "01",
    ]


def test_split_without_separators():
    assert split_pieces("hq6500a") == ["hq", "6500", "a"]


def test_split_mixed_separators():
    assert split_pieces("ab_cd-12") == ["ab", "_", "cd", "-", "12"]


def test_pieces_join_back_to_the_original():
    for name in ("exsite-wing-bld01a-cor-01", "hq6500a", "x__y--1", "wxyz"):
        assert "".join(split_pieces(name)) == name


# --- parse_keep_words ----------------------------------------------------------------------------


def test_keep_words_commas_spaces_and_case():
    assert parse_keep_words(" COR, dst  acc,,hq ") == {"cor", "dst", "acc", "hq"}


def test_keep_words_empty():
    assert parse_keep_words("") == set()


# --- fake_hostnames: shape and keep list ---------------------------------------------------------


def test_fake_keeps_shape_and_changes_name():
    result = fake_hostnames("exsite-wing-bld01a-cor-01", rng=seeded())
    (fake,) = result.fakes
    assert shape(fake) == shape("exsite-wing-bld01a-cor-01")
    assert fake != "exsite-wing-bld01a-cor-01"


def test_kept_pieces_stay():
    result = fake_hostnames("exsite-wing-bld01a-cor-01", {"cor", "bld"}, rng=seeded())
    pieces = split_pieces(result.fakes[0])
    assert pieces[4] == "bld"
    assert pieces[8] == "cor"
    assert pieces[0] != "exsite"


def test_keep_matches_whole_pieces_only():
    # "cor" must not protect the "cor" inside "score".
    fake = fake_hostnames("score-cor-01", {"cor"}, rng=seeded()).fakes[0]
    assert split_pieces(fake)[0] != "score"
    assert split_pieces(fake)[2] == "cor"


def test_no_separator_name_keeps_prefix():
    fake = fake_hostnames("hq6500a", {"hq"}, rng=seeded()).fakes[0]
    assert fake.startswith("hq")
    assert shape(fake) == "aa9999a"
    assert fake != "hq6500a"


def test_short_letters_only_name_is_faked():
    fake = fake_hostnames("wxyz", rng=seeded()).fakes[0]
    assert shape(fake) == "aaaa" and fake != "wxyz"


def test_keep_matching_ignores_case():
    fake = fake_hostnames("SITE-COR-01", {"cor"}, rng=seeded()).fakes[0]
    assert split_pieces(fake)[2] == "COR"


# --- fake_hostnames: lines, repeats, uniqueness --------------------------------------------------


def test_blank_lines_stay_blank_and_order_is_kept():
    text = "alpha-cor-01\n\n  \nbravo-dst-02\n"
    result = fake_hostnames(text, {"cor", "dst"}, rng=seeded())
    assert len(result.fakes) == 4
    assert result.fakes[1] == "" and result.fakes[2] == ""
    assert "-cor-" in result.fakes[0] and "-dst-" in result.fakes[3]


def test_same_name_gets_same_fake_ignoring_case():
    result = fake_hostnames("lab-sw-01\nother-sw-02\nLAB-SW-01", rng=seeded())
    first, _, third = result.fakes
    assert first.upper() == third
    assert third.isupper()


def test_different_names_get_different_fakes():
    names = [f"bldg-acc-{n:04d}" for n in range(1000)]
    fakes = fake_hostnames("\n".join(names), {"bldg", "acc"}, rng=seeded()).fakes
    assert len(set(fakes)) == 1000


def test_too_few_possible_fakes_is_refused():
    # Only 10 fakes are possible ("x-0" .. "x-9"), and 9 of them are real names from this paste,
    # which leaves 1 fake for 9 names. It must fail clearly, not loop forever or reuse real names.
    names = [f"x-{n}" for n in range(9)]
    with pytest.raises(HostnameFakerError, match="Ran out of unique fakes"):
        fake_hostnames("\n".join(names), {"x"}, rng=seeded())


def test_fakes_avoid_real_names_when_possible():
    names = ["x-1", "x-2"]
    for seed in range(50):
        fakes = fake_hostnames("\n".join(names), {"x"}, rng=random.Random(seed)).fakes
        assert not set(fakes) & set(names)


def test_all_pieces_kept_is_reported():
    result = fake_hostnames("lab-cor-01\ncor\n", {"cor"}, rng=seeded())
    assert result.fakes[1] == "cor"
    assert result.unchanged == [(2, "cor")]


# --- fake_hostnames: case ------------------------------------------------------------------------


def test_case_same_copies_each_character():
    fake = fake_hostnames("Lab-SW-ab01", rng=seeded()).fakes[0]
    assert fake[0].isupper() and fake[1].islower()
    assert fake[4:6].isupper() and fake[7:9].islower()


def test_case_upper_and_lower():
    assert fake_hostnames("lab-sw-01", case="upper", rng=seeded()).fakes[0].isupper()
    assert fake_hostnames("LAB-SW-01", case="lower", rng=seeded()).fakes[0].islower()


def test_unknown_case_is_refused():
    with pytest.raises(HostnameFakerError, match="Unknown case"):
        fake_hostnames("lab-sw-01", case="title")


# --- fake_hostnames: input limits ----------------------------------------------------------------


def test_empty_paste_is_refused():
    with pytest.raises(HostnameFakerError, match="at least one hostname"):
        fake_hostnames(" \n\n")


def test_too_many_lines_is_refused():
    with pytest.raises(HostnameFakerError, match="at most"):
        fake_hostnames("a\n" * (MAX_LINES + 1))


def test_windows_line_endings_and_stray_spaces():
    result = fake_hostnames("  lab-sw-01 \r\nlab-sw-02\t\r\n", {"lab", "sw"}, rng=seeded())
    assert len(result.fakes) == 2
    assert all(f.startswith("lab-sw-") and len(f) == 9 for f in result.fakes)
