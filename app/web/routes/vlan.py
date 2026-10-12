"""
vlan.py — the VLAN list tab's form.

POST /vlan  with vlans (numbers and ranges, separated by commas, spaces or
            new lines) -> the same VLANs compressed ("10,20-23,100") and
            one per line, plus the free (unused) IDs between the lowest and
            highest, all at once, each with Copy/Download. Anything that
            isn't a VLAN is listed as a warning.
The work is done by app/tools/vlan_list.py.
"""

from fastapi import APIRouter, Request

from app.tools.vlan_list import MAX_VLAN, MIN_VLAN, VLANListError, compress, free_vlans, parse_vlans
from app.web.forms import read_large_form
from app.web.responses import OutputBlock, ToolResult, cap_warnings, tool_response

router = APIRouter()


@router.post("/vlan")
async def vlan(request: Request):
    # Read by hand so a big paste (over 1 MB) is accepted, as in the converter.
    data = await read_large_form(request)
    vlans = data.get("vlans", "")
    form = {"vlans": vlans}

    try:
        result = parse_vlans(vlans)
    except VLANListError as error:
        return tool_response(request, ToolResult(kind="vlan", error=str(error)), form)

    count = len(result.vlans)
    free = free_vlans(result.vlans)
    summary = f"{count:,} VLAN{'s' if count != 1 else ''}"
    if count >= 2:
        # e.g. "250 VLANs, 37 free between 2 and 1195"
        summary += f", {len(free):,} free between {result.vlans[0]} and {result.vlans[-1]}"
    if result.invalid:
        summary += f", {len(result.invalid):,} item{'s' if len(result.invalid) != 1 else ''} skipped"

    warnings = cap_warnings([f"Skipped '{text}': {reason}" for text, reason in result.invalid])
    if result.invalid and not result.vlans:
        warnings.append(f"Nothing valid found. VLANs are numbers from {MIN_VLAN} to {MAX_VLAN}.")

    blocks = [
        # One long line: shown wrapping only after commas (wrap_at_commas), copied as one line.
        OutputBlock(
            download="vlan-compressed",
            lines=[compress(result.vlans)] if count else [],
            title="Compressed",
            wrap_at_commas=True,
        ),
        OutputBlock(download="vlan-expanded", lines=[str(v) for v in result.vlans], title="One per line"),
        # The gaps, compressed; no box at all when there are none (empty blocks aren't shown).
        OutputBlock(
            download="vlan-free",
            lines=[compress(free)] if free else [],
            title="Free VLANs",  # the summary line says "between X and Y"
            wrap_at_commas=True,
        ),
    ]
    response = ToolResult(kind="vlan", summary=summary, warnings=warnings, blocks=blocks)
    return tool_response(request, response, form)
