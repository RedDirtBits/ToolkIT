"""Replace a pasted list of real hostnames with fake ones of the same shape.

The job: a spreadsheet column of real hostnames goes in, a column of fakes comes out, one per line
and in the same order, so it can be pasted straight back over the real column.

How a hostname is faked:

1. It's cut into "pieces" at two kinds of boundary:
     - separators (anything that isn't a letter or digit, usually - or _), which are kept as-is;
     - changes between letters and digits, so names without separators still have parts.

       exsite-wing-bld01a-cor-01  ->  exsite | - | wing | - | bld | 01 | a | - | cor | - | 01
       hq6500a                   ->  hq | 6500 | a

2. A piece on the user's keep list (whole piece, ignoring case) stays as it is. With "cor" and "hq"
   kept, the device role and site prefix stay readable.
3. Every other piece is replaced by random characters of the same kind and length: letters become
   random letters, digits become random digits.

       exsite-wing-bld01a-cor-01  ->  wqzte-mlax-rvk37f-cor-58
       hq6500a                   ->  hq2914k

Rules:
- Blank lines stay blank, so the output lines up row for row with the input.
- The same real hostname always gets the same fake (ignoring case), so a spreadsheet stays consistent.
- Two different real hostnames never get the same fake, and a fake is never one of the real
  hostnames from the paste.
- A line whose pieces are all on the keep list can't be faked. It's reported, not silently passed on.

Pure Python, no web code.
"""

from __future__ import annotations

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

# How many times to re-roll a fake that clashes with one already used before giving up. A clash is
# rare unless a shape has very few possible fakes (e.g. "a-1" with "a" kept: only 10), and then
# giving up with a clear message is the right answer anyway.
_MAX_TRIES = 200

# One piece = a run of letters, OR a run of digits, OR a run of anything else (the separators).
# findall() returns the runs in order, so joining them gives back the original string exactly.
_PIECE = re.compile(r"[A-Za-z]+|[0-9]+|[^A-Za-z0-9]+")


class HostnameFakerError(ValueError):
    """A request we can't fulfil. The message is written for the user and is safe to show as-is."""


@dataclass
class FakeResult:
    """What fake_hostnames() produced.

    `fakes` has exactly one entry per input line (blank for blank lines), so it lines up with the
    spreadsheet. `unchanged` lists the lines that couldn't be faked because every piece was kept,
    as (line number, text) pairs, so the page can warn about them.
    """

    fakes: list[str] = field(default_factory=list)
    unchanged: list[tuple[int, str]] = field(default_factory=list)


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

    # Every real hostname in the paste, lowercase. A fake must never be one of these, or the "fake"
    # list could contain a real device name.
    real_names = {line.lower() for line in lines if line}

    # real hostname (lowercase) -> its fake (lowercase). This is what makes repeats consistent.
    fake_for: dict[str, str] = {}
    # Every fake handed out so far, so no two real hostnames share one.
    used_fakes: set[str] = set()

    result = FakeResult()
    for line_number, line in enumerate(lines, start=1):
        if not line:
            result.fakes.append("")
            continue

        key = line.lower()
        if key not in fake_for:
            fake_for[key] = _new_fake(key, keep_words, real_names, used_fakes, rng)
            used_fakes.add(fake_for[key])
        fake = fake_for[key]

        if fake == key:
            # Nothing in this line could be faked (every piece is on the keep list).
            result.unchanged.append((line_number, line))

        result.fakes.append(_apply_case(fake, line, case))
    return result


def _new_fake(
    hostname: str,
    keep_words: set[str],
    real_names: set[str],
    used_fakes: set[str],
    rng: random.Random,
) -> str:
    """Make one fake for a (lowercase) hostname that doesn't clash with anything used so far."""
    pieces = split_pieces(hostname)

    # If every letter/digit piece is kept, there's nothing to randomize: return the name unchanged
    # and let the caller report it. (Re-rolling would just produce the same name forever.)
    if all(_is_separator(piece) or piece in keep_words for piece in pieces):
        return hostname

    for _ in range(_MAX_TRIES):
        fake = "".join(_fake_piece(piece, keep_words, rng) for piece in pieces)
        if fake not in used_fakes and fake not in real_names:
            return fake
    raise HostnameFakerError(
        f"Ran out of unique fakes for hostnames shaped like '{hostname}': there are too many of "
        "them for the few characters left to randomize. Keep fewer of its pieces."
    )


def _fake_piece(piece: str, keep_words: set[str], rng: random.Random) -> str:
    """Return a kept piece or separator as-is; replace any other piece with random characters."""
    if piece in keep_words or _is_separator(piece):
        return piece
    if piece[0] in string.digits:
        # rng.choices(population, k=n) picks n items, repeats allowed: "6500" -> e.g. "2914".
        return "".join(rng.choices(string.digits, k=len(piece)))
    # Otherwise it's a letter run.
    return "".join(rng.choices(string.ascii_lowercase, k=len(piece)))


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
