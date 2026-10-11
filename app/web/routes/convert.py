"""
convert.py — the MAC converter tab's form.

POST /convert  with macs (pasted, one per line), upper -> the same MACs in
EVERY format at once (colon, hyphen, dotted), one box each with its own
Copy button, so there's no format to choose first. Lines that aren't MACs
are listed as warnings.
The work is done by app/tools/mac_format.py.
"""

from fastapi import APIRouter, Request

from app import settings
from app.tools.mac_format import convert_all_formats
from app.web.forms import is_checked, read_large_form
from app.web.responses import OutputBlock, ToolResult, cap_warnings, tool_response

router = APIRouter()

# The heading over each format's box.
FORMAT_TITLES = {
    "colon": "Colon",
    "hyphen": "Hyphen",
    "dotted": "Cisco dotted",
}


@router.post("/convert")
async def convert(request: Request):
    # Read by hand rather than with Form(...) parameters, so a paste larger
    # than 1 MB is accepted (see read_large_form).
    data = await read_large_form(request)
    macs = data.get("macs", "")
    upper = data.get("upper", "")
    form = {"macs": macs, "upper": upper}

    def refuse(message: str):
        return tool_response(request, ToolResult(kind="convert", error=message), form)

    if not macs.strip():
        return refuse("Paste one or more MAC addresses, one per line.")
    if len(macs.splitlines()) > settings.MAX_CONVERT_LINES:
        return refuse(f"That's more than {settings.MAX_CONVERT_LINES:,} lines; convert it in parts.")
    converted = convert_all_formats(macs, is_checked(upper))

    warnings = cap_warnings(
        [f"Line {number} skipped, not a MAC: {text}" for number, text in converted.errors]
    )

    # Every format holds the same MACs, so any one of them gives the count.
    count = len(converted.by_format["colon"])
    summary = f"{count:,} converted"
    if converted.errors:
        summary += f", {len(converted.errors):,} skipped"
    blocks = [
        OutputBlock(download=f"convert-{style}", lines=lines, title=FORMAT_TITLES.get(style, style))
        for style, lines in converted.by_format.items()
    ]
    result = ToolResult(kind="convert", summary=summary, blocks=blocks, warnings=warnings)
    return tool_response(request, result, form)
