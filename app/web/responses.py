"""
responses.py — how every tool sends its result back to the browser.

Each tool's form can arrive two ways:

  1. From htmx (the normal case). htmx adds an "HX-Request" header and only
     wants the small result block, which it drops into the page in place.
     The form, the other tabs and their results stay exactly as they were.

  2. As a plain form post, if JavaScript is off or htmx failed to load.
     Then the browser expects a whole new page, so we render the full page
     with this tool's tab selected, its form filled back in, and its result
     shown. Slower and other tabs' results are lost, but it still works.

tool_response() makes that choice, so each route just builds a ToolResult.
"""

from dataclasses import dataclass, field

from fastapi import Request

from app.web.templating import render

# Show at most this many warnings; a paste of mostly junk would otherwise
# bury the result under hundreds of them.
MAX_WARNINGS_SHOWN = 20


@dataclass
class OutputBlock:
    """One output box with its own Copy and Download buttons.

    The generators produce one block; the MAC converter one per format.

    download  key into routes/download.py's FILE_NAMES; also makes the box's id unique
    lines     the output, one item per line
    title     heading over the box ("Colon"), or "" for none
    wrap_at_commas  show the text as page text that wraps only after commas (the
              VLAN list's one long compressed line), instead of a text box that
              would wrap mid-number; Copy and Download still use the exact text
    """

    download: str
    lines: list[str]
    title: str = ""
    wrap_at_commas: bool = False


@dataclass
class Table:
    """A results table (OUI lookups and vendor searches, the subnet split), shown above the output boxes.

    headers   the column titles
    rows      one list of cell texts per row
    note      a line under the table, e.g. "first 500 rows shown"
    """

    headers: list[str]
    rows: list[list[str]]
    note: str = ""


@dataclass
class ToolResult:
    """What one tool produced, ready for the _result.html template.

    kind      which result this is: the tab key ("ip", "mac", ...), or for a tab with
              several forms, one name per form ("oui_lookup", "oui_search")
    tab       the tab it belongs to, if that isn't the same as kind
    error     a message for the user if the request was refused (then blocks is empty)
    summary   one line describing the result, e.g. "300 addresses from 172.22.14.0/23"
    blocks    the output boxes
    warnings  things worth knowing that didn't stop the result (e.g. skipped lines)
    table     an optional results table
    details   optional (label, value) rows, each value with its own Copy button
              (the subnet calculator)
    """

    kind: str
    tab: str = ""
    error: str | None = None
    summary: str = ""
    blocks: list[OutputBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    table: Table | None = None
    details: list[tuple[str, str]] = field(default_factory=list)


def cap_warnings(warnings: list[str]) -> list[str]:
    """Keep the first MAX_WARNINGS_SHOWN warnings and say how many were left out."""
    if len(warnings) <= MAX_WARNINGS_SHOWN:
        return warnings
    hidden = len(warnings) - MAX_WARNINGS_SHOWN
    return warnings[:MAX_WARNINGS_SHOWN] + [f"... and {hidden:,} more."]


def tool_response(request: Request, result: ToolResult, form: dict[str, str]):
    """Send just the result block to htmx, or the whole page to a plain form post."""
    # An error is still a normal 200 response: htmx only swaps in 2xx responses
    # by default, and the error message is part of the result block.
    if request.headers.get("HX-Request") == "true":
        return render(request, "_result.html", result=result)
    return render(
        request,
        "index.html",
        tab=result.tab or result.kind,
        # e.g. ip_result / ip_form, which index.html hands to that tab only.
        **{f"{result.kind}_result": result, f"{result.kind}_form": form},
    )
