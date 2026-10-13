"""
hosts.py — the hostname faker tab's form.

POST /hosts  with hostnames (pasted, one per line), keep (words to keep,
e.g. "cor, dst"), case -> one fake hostname per line, in the same order,
blank lines kept, so the result can be pasted straight back over the real
column of a spreadsheet. Lines that couldn't be faked are listed as warnings.
The work is done by app/tools/hostname_faker.py.
"""

from fastapi import APIRouter, Request

from app.tools.hostname_faker import HostnameFakerError, fake_hostnames, parse_keep_words
from app.web.forms import read_large_form
from app.web.responses import OutputBlock, ToolResult, cap_warnings, tool_response

router = APIRouter()


@router.post("/hosts")
async def fake(request: Request):
    # Read by hand rather than with Form(...) parameters, so a paste larger
    # than 1 MB is accepted (see read_large_form).
    data = await read_large_form(request)
    hostnames = data.get("hostnames", "")
    keep = data.get("keep", "")
    case = data.get("case", "same")
    form = {"hostnames": hostnames, "keep": keep, "case": case}

    keep_words = parse_keep_words(keep)
    try:
        faked = fake_hostnames(hostnames, keep_words, case)
    except HostnameFakerError as error:
        return tool_response(request, ToolResult(kind="hosts", error=str(error)), form)

    # Count the real hostnames (not the blank lines) and how many different
    # ones there were, so the summary shows how much repeated.
    names = [line.strip().lower() for line in hostnames.splitlines() if line.strip()]
    summary = f"{len(names):,} hostnames faked ({len(set(names)):,} different)"
    if keep_words:
        summary += f", keeping {', '.join(sorted(keep_words))}"

    warnings = (
        [
            f"Line {number} not faked: every part of it is on the keep list: {text}"
            for number, text in faked.unchanged
        ]
        + [
            f"Line {number}: its fake matches another real hostname from the paste: {text}"
            for number, text in faked.matches_real
        ]
        + [
            f"Line {number} has characters outside A-Z and 0-9 (e.g. accented letters), copied into the "
            f"fake unchanged: check it before sharing: {text}"
            for number, text in faked.non_ascii
        ]
    )

    block = OutputBlock(download="hosts", lines=faked.fakes)
    result = ToolResult(kind="hosts", summary=summary, blocks=[block], warnings=cap_warnings(warnings))
    return tool_response(request, result, form)
