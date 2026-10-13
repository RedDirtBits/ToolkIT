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

    # One warning for all of them, not one per line: an ACL of "host" entries (x.x.x.x 0.0.0.0)
    # would otherwise fill the page with the same message.
    if result.read_as_host:
        count = len(result.read_as_host)
        first_number, first_text = result.read_as_host[0]
        lines = "1 line uses" if count == 1 else f"{count:,} lines use"
        warnings.append(
            f"{lines} 0.0.0.0 or 255.255.255.255 as the mask or wildcard (first: line {first_number}, "
            f'{first_text}). These are read as a single host (/32), never as "any". If a line meant '
            '"any", replace it with 0.0.0.0/0.'
        )

    # Explain the "odd-looking" case where it happens: mostly single addresses (e.g. in-use
    # management IPs) that break into many small blocks, because an exact summary can't bridge
    # the unused addresses between them. Range-shaped lists (what ACLs and prefix lists hold)
    # merge cleanly and don't need the note.
    singles = sum(1 for item in result.original if item.prefixlen == 32)
    if len(result.summary) > 1 and singles * 2 > len(result.original):
        warnings.append(
            f"Note: these are mostly single addresses, so the exact summary has {len(result.summary):,} "
            "small blocks: it never includes unused addresses, and gaps between your addresses "
            "can't be bridged. That's right for an ACL that must allow only these hosts. To see "
            'the one network they sit in, use "All fit in" below.'
        )

    details = []
    if result.covering is not None:
        details = [
            ("All fit in (one block)", format_block(result.covering, style)),
            ("Extra addresses", f"{result.extra:,}" if result.extra else "none: an exact fit"),
        ]

    blocks = [
        OutputBlock(
            download="iplist-summary", lines=summary_lines, title="Summarized for ACLs / prefix lists"
        ),
        OutputBlock(
            download="iplist-sorted", lines=[format_item(n) for n in result.sorted], title="Sorted, unique"
        ),
        OutputBlock(
            download="iplist-original",
            lines=[format_item(n) for n in result.original],
            title="Original order, unique",
        ),
    ]
    response = ToolResult(kind="iplist", summary=summary, warnings=warnings, details=details, blocks=blocks)
    return tool_response(request, response, form)
