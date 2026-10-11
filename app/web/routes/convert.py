"""
convert.py — the MAC converter tab's form.

POST /convert  with macs (pasted, one per line), style, upper -> the same
MACs in the chosen format. Lines that aren't MACs are listed as warnings.
The work is done by app/tools/mac_format.py.
"""

from fastapi import APIRouter, Request

from app import settings
from app.tools.mac_format import MACError, convert_lines
from app.web.forms import is_checked, read_large_form
from app.web.responses import ToolResult, tool_response

router = APIRouter()

# Show at most this many skipped lines; a paste of mostly junk would
# otherwise bury the result under hundreds of warnings.
MAX_WARNINGS_SHOWN = 20


@router.post("/convert")
async def convert(request: Request):
    # Read by hand rather than with Form(...) parameters, so a paste larger
    # than 1 MB is accepted (see read_large_form).
    data = await read_large_form(request)
    macs = data.get("macs", "")
    style = data.get("style", "colon")
    upper = data.get("upper", "")
    form = {"macs": macs, "style": style, "upper": upper}

    def refuse(message: str):
        return tool_response(request, ToolResult(kind="convert", error=message), form)

    if not macs.strip():
        return refuse("Paste one or more MAC addresses, one per line.")
    if len(macs.splitlines()) > settings.MAX_CONVERT_LINES:
        return refuse(f"That's more than {settings.MAX_CONVERT_LINES:,} lines; convert it in parts.")
    try:
        converted = convert_lines(macs, style, is_checked(upper))
    except MACError as error:
        return refuse(str(error))

    warnings = [f"Line {number} skipped, not a MAC: {text}" for number, text in converted.errors]
    if len(warnings) > MAX_WARNINGS_SHOWN:
        hidden = len(warnings) - MAX_WARNINGS_SHOWN
        warnings = warnings[:MAX_WARNINGS_SHOWN] + [f"... and {hidden:,} more skipped lines."]

    summary = f"{len(converted.converted):,} converted"
    if converted.errors:
        summary += f", {len(converted.errors):,} skipped"
    result = ToolResult(kind="convert", summary=summary, lines=converted.converted, warnings=warnings)
    return tool_response(request, result, form)
