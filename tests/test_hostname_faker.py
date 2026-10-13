"""Tests for app/tools/hostname_faker.py.

All hostnames here are invented. Like the other tool tests, these check rules that must always hold
(same shape, kept pieces kept, no repeats, no real names leaking) rather than specific random
values, and pass a seeded random generator so failures can be reproduced.
"""

import random
import string

import pytest

from app.tools.hostname_faker import (
    HostnameFakerError,
    fake_hostnames,
    parse_keep_words,
    split_pieces,
)
from app.tools.limits import MAX_ITEMS


def seeded() -> random.Random:
    return random.Random(1234)


def shape(hostname: str) -> str:
    """Reduce a hostname to its shape: a = letter, 9 = digit, separators as-is."""
    return "".join("a" if c in string.ascii_letters else "9" if c in string.digits else c for c in hostname)


# --- split_pieces --------------------------------------------------------------------------------


def test_split_at_separators_and_letter_digit_changes():
    # Kept on one line on purpose, so it reads like the name being cut up.
    assert split_pieces("exsite-wing-bld01a-cor-01") == [
        "exsite", "-", "wing", "-", "bld", "01", "a", "-", "cor", "-", "01",
    ]  # fmt: skip


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


def test_short_piece_size_running_out_reuses_real_values_and_reports_it():
    # Only 10 one-digit values exist and 9 of them are real here, so after "9" is dealt the deck
    # must reuse real values. Fakes must still all differ, and any that equal a real name are named.
    names = [f"x-{n}" for n in range(9)]
    result = fake_hostnames("\n".join(names), {"x"}, rng=seeded())
    assert len(set(result.fakes)) == 9
    clashing = {text for _, text in result.matches_real}
    assert clashing == {real for real, fake in zip(names, result.fakes) if fake in names}
    assert len(clashing) == 8  # one line got "x-9", the other 8 had to reuse real digits


def test_real_pieces_avoided_when_there_is_room():
    # 2-digit pieces: 100 values, only 3 real, so no fake piece should be a real one.
    names = ["sw-01", "sw-02", "sw-03"]
    for seed in range(50):
        result = fake_hostnames("\n".join(names), {"sw"}, rng=random.Random(seed))
        assert not {f[-2:] for f in result.fakes} & {"01", "02", "03"}
        assert result.matches_real == []


# --- fake_hostnames: consistent pieces ------------------------------------------------------------


def test_same_piece_gets_same_fake_everywhere():
    text = "exsite-wing-bld01a-cor-01\nexsite-wing-bld01a-dst-01\nexsite-lab-bld02a-acc-07"
    a, b, c = fake_hostnames(text, {"cor", "dst", "acc"}, rng=seeded()).fakes
    # Rows 1 and 2 share everything but the role, so their fakes must too.
    assert a.replace("-cor-", "-?-") == b.replace("-dst-", "-?-")
    # Row 3 shares the site "exsite" and the "bld" and "a" pieces, but not "wing" or "01".
    pa, pc = split_pieces(a), split_pieces(c)
    assert pa[0] == pc[0] and pa[4] == pc[4] and pa[6] == pc[6]
    assert pa[2] != pc[2] and pa[5] != pc[5]


def test_different_pieces_get_different_fakes():
    text = "\n".join(f"{site}-sw" for site in ("ab", "cd", "ef", "gh", "ij", "kl"))
    fakes = fake_hostnames(text, {"sw"}, rng=seeded()).fakes
    assert len({f.split("-")[0] for f in fakes}) == 6


def test_fake_piece_is_never_a_keep_word():
    # "cor" is kept; the 3-letter site pieces must never be faked into "cor".
    text = "\n".join(f"{a}{b}x-cor" for a in "abcdefgh" for b in "abcdefgh")
    for fake in fake_hostnames(text, {"cor"}, rng=seeded()).fakes:
        assert split_pieces(fake)[0] != "cor"


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
        fake_hostnames("a\n" * (MAX_ITEMS + 1))


def test_windows_line_endings_and_stray_spaces():
    result = fake_hostnames("  lab-sw-01 \r\nlab-sw-02\t\r\n", {"lab", "sw"}, rng=seeded())
    assert len(result.fakes) == 2
    assert all(f.startswith("lab-sw-") and len(f) == 9 for f in result.fakes)


def test_maximum_paste_with_mostly_real_big_pieces():
    # 65,534 different 5-digit numbers fill most of the 100,000 possible values, so the random path
    # must fall back to reusing real values instead of failing. Every fake must still be different.
    text = "\n".join(f"acc-{n:05d}" for n in range(MAX_ITEMS))
    result = fake_hostnames(text, {"acc"}, rng=seeded())
    assert len(set(result.fakes)) == MAX_ITEMS


# --- non-ASCII characters --------------------------------------------------------------------------


def test_non_ascii_lines_are_reported():
    # Invented names. The "ö" isn't an A-Z letter, so it's a separator and survives into the fake.
    result = fake_hostnames("bölla-sw-01\n\nlab-sw-02", rng=seeded())
    assert result.non_ascii == [(1, "bölla-sw-01")]
    assert "ö" in result.fakes[0]
    assert result.fakes[0] != "bölla-sw-01"


def test_ascii_lines_are_not_reported():
    assert fake_hostnames("lab-sw-01\nLAB_SW_02", rng=seeded()).non_ascii == []


def test_case_copy_stays_aligned_with_letters_that_lower_changes_length():
    # "İ".lower() is two characters; lowercasing it would shift the case copy by one.
    result = fake_hostnames("LAB-İX-01", rng=seeded())
    fake = result.fakes[0]
    assert len(fake) == len("LAB-İX-01")
    assert fake[4] == "İ"
    assert shape(fake) == shape("LAB-İX-01")
    assert fake[:3].isupper() and fake[5].isupper()
