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


@dataclass
class ToolResult:
    """What one tool produced, ready for the _result.html template.

    kind      the tool's tab key ("ip", "mac", "convert"); also picks the download file name
    error     a message for the user if the request was refused (then lines is empty)
    summary   one line describing the result, e.g. "300 addresses from 172.22.14.0/23"
    lines     the output, one item per line
    warnings  things worth knowing that didn't stop the result (e.g. skipped lines)
    """

    kind: str
    error: str | None = None
    summary: str = ""
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def tool_response(request: Request, result: ToolResult, form: dict[str, str]):
    """Send just the result block to htmx, or the whole page to a plain form post."""
    # An error is still a normal 200 response: htmx only swaps in 2xx responses
    # by default, and the error message is part of the result block.
    if request.headers.get("HX-Request") == "true":
        return render(request, "_result.html", result=result)
    return render(
        request,
        "index.html",
        tab=result.kind,
        # e.g. ip_result / ip_form, which index.html hands to that tab only.
        **{f"{result.kind}_result": result, f"{result.kind}_form": form},
    )
