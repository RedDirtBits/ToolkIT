"""
subnet.py — the subnet calculator tab's form.

POST /subnet  with address ("192.168.4.17/22", "... 255.255.252.0", or an
              ACL wildcard) and optionally split ("/26" or "8")
              -> every value about that subnet, each with its own Copy
              button; with a split, also the list of smaller subnets.
The work is done by app/tools/subnet_calc.py.
"""

from fastapi import APIRouter, Form, Request

from app import settings
from app.tools.subnet_calc import SubnetError, calculate, parse_split, read_as_single_host, split_network
from app.web.responses import OutputBlock, Table, ToolResult, tool_response

router = APIRouter()


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
        rows = [_subnet_row(s) for s in subnets[: settings.MAX_TABLE_ROWS]]
        note = (
            f"First {settings.MAX_TABLE_ROWS:,} of {len(subnets):,} shown; the Subnets box has them all."
            if len(subnets) > settings.MAX_TABLE_ROWS
            else ""
        )
        table = Table(headers=["Subnet", "Usable range", "Broadcast"], rows=rows, note=note)
        blocks = [OutputBlock(download="subnets", lines=[str(s) for s in subnets], title="Subnets")]

    # 0.0.0.0 and 255.255.255.255 are read as one host, but each also means "any" in the other
    # notation (mask 0.0.0.0, wildcard 255.255.255.255). Say which way it was read.
    warnings = []
    size = read_as_single_host(address)
    if size:
        other = "mask" if size == "0.0.0.0" else "wildcard"
        warnings.append(
            f'Read {size} as a single host (/32). As a {other} it would mean "any"; '
            "if that's what you meant, type 0.0.0.0/0."
        )

    result = ToolResult(
        kind="subnet", summary=summary, warnings=warnings, details=details, table=table, blocks=blocks
    )
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
