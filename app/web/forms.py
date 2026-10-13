"""
forms.py — turn raw form text into values the tools can use.

Every form field arrives as text. Rather than let FastAPI reject a bad
number with a technical error page, the routes take the text as-is and
call these helpers, which give messages a person can act on.
"""

from fastapi import Request

from app import settings
from app.tools.limits import MAX_ITEMS


class FormError(ValueError):
    """A form value we can't use. The message is safe to show the user."""


def parse_count(text: str, required: bool = False) -> int | None:
    """Read the "count" box. Empty gives None (or an error if required).

    Thousands separators and spaces are allowed: "1,000", "1 000" and "1000"
    all mean 1000.
    """
    cleaned = text.strip().replace(",", "").replace(" ", "").replace("_", "")
    if not cleaned:
        if required:
            raise FormError("Give a count.")
        return None
    # isdigit() rejects "-5", "1.5" and "abc". isascii() is needed too, because
    # isdigit() also accepts characters like "²" that int() can't read.
    # (A count of 0 passes here, and the tool itself refuses it.)
    if not (cleaned.isascii() and cleaned.isdigit()):
        raise FormError(f"'{_shorten(text.strip())}' isn't a whole number.")
    # Check the LENGTH before converting. Python refuses to turn a string of
    # more than 4,300 digits into an int (a safety limit since 3.11) and raises
    # a plain ValueError, which the routes don't catch: the page would freeze
    # on a mis-paste. No tool accepts more than MAX_ITEMS, so a number with
    # more digits than _MAX_COUNT_DIGITS is too large anyway. Anything shorter
    # reaches the tool, which refuses it with its own, exact message
    # ("at most 65,534").
    if len(cleaned) > _MAX_COUNT_DIGITS:
        raise FormError(f"'{_shorten(cleaned)}' is far too large for a count.")
    return int(cleaned)


# One digit more than the largest count any tool accepts (65,534 has 5, so 6:
# up to 999,999). Worked out from MAX_ITEMS, so raising the limit can never
# leave this cap blocking counts the tools would accept. Still far below the
# 4,300 digits where int() gives up.
_MAX_COUNT_DIGITS = len(str(MAX_ITEMS)) + 1


def _shorten(text: str, limit: int = 20) -> str:
    """Cut a long value for an error message: a 5,000-digit paste isn't worth echoing in full."""
    return text if len(text) <= limit else text[:limit] + "…"


def is_checked(value: str) -> bool:
    """A checkbox sends "on" when ticked and nothing at all when not."""
    return value == "on"


async def read_large_form(request: Request) -> dict[str, str]:
    """Read a form whose fields may be bigger than Starlette's 1 MB default.

    Used by the routes that receive whole result lists (download) or big
    pastes (converter). "async" and "await" are needed because the form is
    read from the network as it arrives; the route must be async too.
    Only text fields are kept (these forms have no file uploads).
    """
    form = await request.form(max_part_size=settings.MAX_FORM_FIELD_BYTES)
    return {key: value for key, value in form.items() if isinstance(value, str)}
