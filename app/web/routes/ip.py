"""
ip.py — the IP generator tab's form.

POST /ip  with count, network and style -> random IPv4 addresses.
The work is done by app/tools/ip_generator.py; this file only reads the
form, calls it, and describes the result.
"""

import ipaddress

from fastapi import APIRouter, Form, Request

from app.tools.ip_generator import (
    IPGeneratorError,
    format_ips,
    generate_ips,
    host_bits_cleared,
    parse_target,
)
from app.web.forms import FormError, parse_count
from app.web.responses import OutputBlock, ToolResult, tool_response

router = APIRouter()


@router.post("/ip")
def generate(
    request: Request,
    count: str = Form(""),
    network: str = Form(""),
    style: str = Form("plain"),
):
    # Kept so a no-JavaScript full page can fill the form back in.
    form = {"count": count, "network": network, "style": style}
    try:
        target = parse_target(network)
        generated = generate_ips(count=parse_count(count), target=target)
        lines = format_ips(generated, style)
    except (IPGeneratorError, FormError) as error:
        return tool_response(request, ToolResult(kind="ip", error=str(error)), form)

    net = generated.network
    usable = net.num_addresses - 2
    # Say where the network came from, since it isn't always what was typed.
    if target is None:
        origin = "random private network"
    elif isinstance(target, ipaddress.IPv4Address):
        origin = f"sized for the count, starting at {target}"
    elif host_bits_cleared(network):
        # e.g. 192.168.5.9/22 typed: the tool cleared the host bits to 192.168.4.0.
        origin = f"rounded down from {network.strip()}"
    else:
        origin = ""
    summary = f"{len(lines):,} addresses from {net} (mask {net.netmask}, {usable:,} usable)"
    if origin:
        summary += f" · {origin}"
    result = ToolResult(kind="ip", summary=summary, blocks=[OutputBlock(download="ip", lines=lines)])
    return tool_response(request, result, form)
