"""
subnet.py — the subnet calculator tab's form.

POST /subnet  with address ("192.168.4.17/22", "... 255.255.252.0", or an
              ACL wildcard) and optionally split ("/26" or "8")
              -> every value about that subnet, each with its own Copy
              button; with a split, also the list of smaller subnets.
The work is done by app/tools/subnet_calc.py.
"""

from fastapi import APIRouter, Form, Request

from app.tools.subnet_calc import SubnetError, calculate, parse_split, split_network
from app.web.responses import OutputBlock, Table, ToolResult, tool_response

router = APIRouter()

# Show at most this many subnets in the table; the Subnets box has them all.
MAX_TABLE_ROWS = 500


@router.post("/subnet")
def subnet(request: Request, address: str = Form(""), split: str = Form("")):
    form = {"address": address, "split": split}
    try:
        info = calculate(address)
        new_prefix, count = parse_split(split)
        subnets = (
            split_network(info.network, new_prefix, count)
            if new_prefix is not None or count is not None
            else []
        )
    except SubnetError as error:
        return tool_response(request, ToolResult(kind="subnet", error=str(error)), form)

    if info.broadcast is not None:
        broadcast = str(info.broadcast)
    elif info.prefix == 31:
        broadcast = "None (/31: point-to-point link, both addresses usable, RFC 3021)"
    else:
        broadcast = "None (/32: a single host)"

    # (label, value) pairs, shown one per row, each value with a Copy button.
    details = [
        ("Network", str(info.network)),
        ("Subnet mask", str(info.netmask)),
        ("Wildcard mask", str(info.wildcard)),
        ("Prefix length", f"/{info.prefix}"),
        ("Broadcast", broadcast),
        ("First usable", str(info.first_usable)),
        ("Last usable", str(info.last_usable)),
        ("Usable hosts", f"{info.usable_hosts:,}"),
        ("Total addresses", f"{info.total_addresses:,}"),
        ("Address type", info.address_type),
    ]
    summary = f"{info.address} is in {info.network}"

    table = None
    blocks = []
    if subnets:
        summary += f", split into {len(subnets):,} × /{subnets[0].prefixlen}"
        rows = [_subnet_row(s) for s in subnets[:MAX_TABLE_ROWS]]
        note = (
            f"First {MAX_TABLE_ROWS:,} of {len(subnets):,} shown; the Subnets box has them all."
            if len(subnets) > MAX_TABLE_ROWS
            else ""
        )
        table = Table(headers=["Subnet", "Usable range", "Broadcast"], rows=rows, note=note)
        blocks = [OutputBlock(download="subnets", lines=[str(s) for s in subnets], title="Subnets")]

    result = ToolResult(kind="subnet", summary=summary, details=details, table=table, blocks=blocks)
    return tool_response(request, result, form)


def _subnet_row(network) -> list[str]:
    """One row of the split table: the subnet, its usable range, its broadcast."""
    if network.prefixlen >= 31:
        first, last, broadcast = network.network_address, network.broadcast_address, "none"
    else:
        first, last = network.network_address + 1, network.broadcast_address - 1
        broadcast = str(network.broadcast_address)
    usable = str(first) if first == last else f"{first} – {last}"
    return [str(network), usable, broadcast]
