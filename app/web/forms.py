"""
forms.py — turn raw form text into values the tools can use.

Every form field arrives as text. Rather than let FastAPI reject a bad
number with a technical error page, the routes take the text as-is and
call these helpers, which give messages a person can act on.
"""

from fastapi import Request

from app import settings


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
        raise FormError(f"'{text.strip()}' isn't a whole number.")
    return int(cleaned)


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
