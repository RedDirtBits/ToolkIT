"""Replace a pasted list of real hostnames with fake ones of the same shape.

The job: a spreadsheet column of real hostnames goes in, a column of fakes comes out, one per line
and in the same order, so it can be pasted straight back over the real column. The fakes keep the
data's *structure* (which devices share a site, a building, a role) while hiding the real names, so
the list can be shared with Claude or colleagues.

How a hostname is faked:

1. It's cut into "pieces" at two kinds of boundary:
     - separators (anything that isn't a letter or digit, usually - or _), which are kept as-is;
     - changes between letters and digits, so names without separators still have parts.

       exsite-wing-bld01a-cor-01  ->  exsite | - | wing | - | bld | 01 | a | - | cor | - | 01
       hq6500a                    ->  hq | 6500 | a

2. A piece on the user's keep list (whole piece, ignoring case) stays as it is. With "cor" and "hq"
   kept, the device role and site prefix stay readable.
3. Every other piece is replaced by random characters of the same kind and length (letters become
   letters, digits become digits), and **the same real piece always gets the same fake piece**:

       exsite-wing-bld01a-cor-01  ->  kautim-bueh-pra30n-cor-58
       exsite-wing-bld01a-dst-01  ->  kautim-bueh-pra30n-dst-58      (same site, still visibly so)
       hq6500a                    ->  hq2914k

Rules:
- Blank lines stay blank, so the output lines up row for row with the input.
- Matching ignores case; each fake is written in the case asked for (by default, the real name's).
- Different real pieces never share a fake piece, so different hostnames never share a fake.
- A fake piece avoids the real pieces and keep words whenever there's room. Only if a short piece
  size runs out of other values (e.g. nearly all 100 two-digit numbers are in use) is a real value
  reused; a fake that ends up equal to a real hostname from the paste is then reported.
- A line whose pieces are all on the keep list can't be faked. It's reported, not silently passed on.

Pure Python, no web code.
"""

from __future__ import annotations

import itertools
import random
import re
import string
from dataclasses import dataclass, field

# Same per-request limit as the other tools (one /16's worth), so a giant paste can't hang the page.
MAX_LINES = 65_534

# The keys the web form sends for the output case.
#   same   copy each real hostname's own case (HQ6500A -> HQ2914K, hq6500a -> hq2914k)
#   lower  everything lowercase
#   upper  everything uppercase
CASES = ("same", "lower", "upper")

# One piece = a run of letters, OR a run of digits, OR a run of anything else (the separators).
# findall() returns the runs in order, so joining them gives back the original string exactly.
_PIECE = re.compile(r"[A-Za-z]+|[0-9]+|[^A-Za-z0-9]+")

# Piece sizes with at most this many possible values (up to 5 digits = 100,000, up to 3 letters =
# 17,576) are dealt from a shuffled "deck" of every value, so they never run out early or slow down
# as they fill up. Bigger sizes (6+ digits, 4+ letters) have so many values that picking at random
# and re-rolling the rare clash is enough. (A 5-digit deck is ~100,000 short strings: a few MB,
# built only if such a piece appears.)
_DECK_LIMIT = 100_000

# How many times to re-roll a clashing random value (big piece sizes only) before giving up.
_MAX_TRIES = 200


class HostnameFakerError(ValueError):
    """A request we can't fulfil. The message is written for the user and is safe to show as-is."""


@dataclass
class FakeResult:
    """What fake_hostnames() produced.

    `fakes` has exactly one entry per input line (blank for blank lines), so it lines up with the
    spreadsheet. The two warning lists hold (line number, text) pairs, so the page can name them:
      `unchanged`     lines that couldn't be faked because every piece is on the keep list;
      `matches_real`  lines whose fake happens to equal a different real hostname from the paste
                      (only possible when a short piece size ran out of unused values).
    """

    fakes: list[str] = field(default_factory=list)
    unchanged: list[tuple[int, str]] = field(default_factory=list)
    matches_real: list[tuple[int, str]] = field(default_factory=list)


def split_pieces(hostname: str) -> list[str]:
    """Cut a hostname into letter runs, digit runs and separator runs (see the module docstring)."""
    return _PIECE.findall(hostname)


def parse_keep_words(text: str) -> set[str]:
    """Read the keep list as typed by the user: words separated by commas and/or spaces.

    Returned lowercase, because matching ignores case ("COR" in a hostname matches "cor" here).
    """
    # re.split on "one or more commas or whitespace" turns "cor, dst  acc" into ["cor", "dst", "acc"];
    # the `if word` drops the empty strings left by leading or trailing commas.
    return {word.lower() for word in re.split(r"[,\s]+", text) if word}


def fake_hostnames(
    text: str,
    keep_words: set[str] | None = None,
    case: str = "same",
    rng: random.Random | None = None,
) -> FakeResult:
    """Fake every hostname in a pasted block (one per line). See the module docstring for the rules.

    `keep_words` should come from parse_keep_words() (lowercase). `rng` lets tests pass a seeded
    random generator; normal use leaves it out and gets a fresh one.
    """
    rng = rng or random.Random()
    keep_words = keep_words or set()

    if case not in CASES:
        raise HostnameFakerError(f"Unknown case '{case}'. Choose one of: {', '.join(CASES)}.")

    # strip() each line: cells copied from a spreadsheet often carry stray spaces or tabs.
    lines = [line.strip() for line in text.splitlines()]
    if not any(lines):
        raise HostnameFakerError("Paste at least one hostname, one per line.")
    if len(lines) > MAX_LINES:
        raise HostnameFakerError(f"Paste at most {MAX_LINES:,} lines at a time.")

    # Everything real in the paste, lowercase: whole names (to spot a fake that equals one) and
    # letter/digit pieces (which fake pieces try to avoid).
    real_names = {line.lower() for line in lines if line}
    real_pieces = {piece for name in real_names for piece in split_pieces(name) if not _is_separator(piece)}
    piece_map = _PieceMap(keep_words, real_pieces, rng)

    result = FakeResult()
    for line_number, line in enumerate(lines, start=1):
        if not line:
            result.fakes.append("")
            continue

        key = line.lower()
        fake = "".join(piece_map.fake(piece) for piece in split_pieces(key))

        if fake == key:
            # Nothing in this line could be faked (every piece is on the keep list).
            result.unchanged.append((line_number, line))
        elif fake in real_names:
            result.matches_real.append((line_number, line))

        result.fakes.append(_apply_case(fake, line, case))
    return result


class _PieceMap:
    """Hands out fake pieces, remembering them so the same real piece always gets the same fake.

    Think of it as a translation dictionary that's filled in as words come up: the first time
    "exsite" is seen it gets a new fake word, and every later "exsite" is looked up, not re-rolled.
    """

    def __init__(self, keep_words: set[str], real_pieces: set[str], rng: random.Random) -> None:
        self.keep_words = keep_words
        self.real_pieces = real_pieces
        self.rng = rng
        self.fake_for: dict[str, str] = {}  # real piece -> its fake piece
        self.used: set[str] = set()  # every fake piece handed out (big piece sizes only)
        self.decks: dict[tuple[str, int], list[str]] = {}  # (alphabet, length) -> values left

    def fake(self, piece: str) -> str:
        """Return the fake for one lowercase piece (separators and kept words come back as-is)."""
        if _is_separator(piece) or piece in self.keep_words:
            return piece
        if piece not in self.fake_for:
            self.fake_for[piece] = self._new_value(piece)
        return self.fake_for[piece]

    def _new_value(self, piece: str) -> str:
        """Pick an unused value of the same kind and length as `piece`."""
        alphabet = string.digits if piece[0] in string.digits else string.ascii_lowercase
        length = len(piece)

        if len(alphabet) ** length <= _DECK_LIMIT:
            deck = self.decks.get((alphabet, length))
            if deck is None:
                deck = self.decks[(alphabet, length)] = self._build_deck(alphabet, length)
            if not deck:
                raise HostnameFakerError(
                    f"There are more different {length}-character pieces like '{piece}' than "
                    "fakes of that size, so they can't all get a different one. Keep fewer words "
                    "of that size."
                )
            # pop() deals from the end of the list, where the preferred (non-real) values are.
            return deck.pop()

        # Big piece size: pick at random and re-roll clashes. Same preference as the deck: first try
        # to avoid real pieces too; if real values fill most of this size (e.g. tens of thousands of
        # different 5-digit numbers pasted), allow them rather than fail.
        for avoid_real in (True, False):
            for _ in range(_MAX_TRIES):
                # rng.choices(population, k=n) picks n items, repeats allowed: e.g. "kauti".
                value = "".join(self.rng.choices(alphabet, k=length))
                if value in self.used or value in self.keep_words:
                    continue
                if avoid_real and value in self.real_pieces:
                    continue
                self.used.add(value)
                return value
        raise HostnameFakerError(
            f"Ran out of unique fakes for pieces like '{piece}'. Paste fewer lines at a time."
        )

    def _build_deck(self, alphabet: str, length: int) -> list[str]:
        """Every value of this kind and length, shuffled, with real pieces at the bottom.

        itertools.product(alphabet, repeat=2) gives every pair: ('0','0'), ('0','1') ... ('9','9').
        Keep words are left out entirely (a fake must never look like a kept role). Real pieces go
        at the start of the list, so pop() only reaches them once every other value is used up.
        """
        values = ["".join(chars) for chars in itertools.product(alphabet, repeat=length)]
        values = [v for v in values if v not in self.keep_words]
        real = [v for v in values if v in self.real_pieces]
        other = [v for v in values if v not in self.real_pieces]
        self.rng.shuffle(real)
        self.rng.shuffle(other)
        return real + other


def _is_separator(piece: str) -> bool:
    """True for a separator run.

    A piece is all of one kind (see _PIECE), so its first character decides. ASCII is checked on
    purpose: str.isalnum() would also call "é" a letter, but _PIECE treats it as a separator.
    """
    return piece[0] not in string.ascii_letters + string.digits


def _apply_case(fake: str, original: str, case: str) -> str:
    """Put the fake (built lowercase) into the requested case.

    For "same", copy the original's case character by character. That works because a fake always
    has exactly the same length as the original, with letters in the same positions.
    """
    if case == "lower":
        return fake
    if case == "upper":
        return fake.upper()
    # zip() pairs up the two strings' characters: (fake[0], original[0]), (fake[1], original[1])...
    return "".join(f.upper() if o.isupper() else f for f, o in zip(fake, original))
