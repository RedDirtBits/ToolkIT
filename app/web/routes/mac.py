"""
mac.py — the MAC generator tab's form.

POST /mac  with count, mode, oui, style, upper -> random MAC addresses.
The work is done by app/tools/mac_generator.py.
"""

from fastapi import APIRouter, Form, Request

from app.tools.mac_format import MACError
from app.tools.mac_generator import MACGeneratorError, generate_formatted
from app.web.forms import FormError, is_checked, parse_count
from app.web.responses import OutputBlock, ToolResult, tool_response

router = APIRouter()

# How each mode is described in the result summary.
MODE_NAMES = {
    "local": "locally administered",
    "random": "random unicast",
    "oui": "OUI-prefixed",
}


@router.post("/mac")
def generate(
    request: Request,
    count: str = Form(""),
    mode: str = Form("local"),
    oui: str = Form(""),
    style: str = Form("colon"),
    upper: str = Form(""),
):
    form = {"count": count, "mode": mode, "oui": oui, "style": style, "upper": upper}
    try:
        number = parse_count(count, required=True)
        # required=True raises FormError instead of returning None; this line tells mypy so.
        assert number is not None
        lines = generate_formatted(
            count=number,
            mode=mode,
            oui_text=oui,
            style=style,
            upper=is_checked(upper),
        )
    except (MACGeneratorError, MACError, FormError) as error:
        return tool_response(request, ToolResult(kind="mac", error=str(error)), form)

    summary = f"{len(lines):,} {MODE_NAMES.get(mode, mode)} MAC addresses"
    if mode == "oui":
        summary += f" with prefix {oui.strip()}"
    result = ToolResult(kind="mac", summary=summary, blocks=[OutputBlock(download="mac", lines=lines)])
    return tool_response(request, result, form)
