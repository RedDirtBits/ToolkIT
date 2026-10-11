"""
iplist.py — the IP list cleanup tab's form.

POST /iplist  with ips (pasted, one address or network per line) and style
              (prefix / mask / wildcard for the summarized blocks)
              -> three boxes at once, each with Copy/Download: the fewest
              blocks covering exactly the input, the unique items sorted,
              and the unique items in their original order; plus the
              smallest single block covering everything. Invalid lines are
              listed as warnings.
The work is done by app/tools/ip_list.py.
"""

from fastapi import APIRouter, Request

from app.tools.ip_list import IPListError, clean_up, format_block, format_item
from app.web.forms import read_large_form
from app.web.responses import OutputBlock, ToolResult, cap_warnings, tool_response

router = APIRouter()


@router.post("/iplist")
async def iplist(request: Request):
    # Read by hand so a big paste (over 1 MB) is accepted, as in the converter.
    data = await read_large_form(request)
    ips = data.get("ips", "")
    style = data.get("style", "prefix")
    form = {"ips": ips, "style": style}

    try:
        result = clean_up(ips)
        summary_lines = [format_block(block, style) for block in result.summary]
    except IPListError as error:
        return tool_response(request, ToolResult(kind="iplist", error=str(error)), form)

    # e.g. "212 lines: 180 unique, 30 duplicates, 2 invalid -> 14 blocks"
    summary = f"{result.total:,} lines: {len(result.original):,} unique"
    if result.duplicates:
        summary += f", {result.duplicates:,} duplicate{'s' if result.duplicates != 1 else ''}"
    if result.invalid:
        summary += f", {len(result.invalid):,} invalid"
    if result.summary:
        summary += f" → {len(result.summary):,} block{'s' if len(result.summary) != 1 else ''}"

    warnings = cap_warnings(
        [f"Line {number} skipped, not an address or network: {text}" for number, text in result.invalid]
    )

    details = []
    if result.covering is not None:
        details = [
            ("All fit in (one block)", format_block(result.covering, style)),
            ("Extra addresses", f"{result.extra:,}" if result.extra else "none: an exact fit"),
        ]

    blocks = [
        OutputBlock(download="iplist-summary", lines=summary_lines, title="Summarized (exact)"),
        OutputBlock(download="iplist-sorted", lines=[format_item(n) for n in result.sorted], title="Sorted, unique"),
        OutputBlock(download="iplist-original", lines=[format_item(n) for n in result.original], title="Original order, unique"),
    ]
    response = ToolResult(kind="iplist", summary=summary, warnings=warnings, details=details, blocks=blocks)
    return tool_response(request, response, form)
