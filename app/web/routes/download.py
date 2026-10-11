"""
download.py — save a tool's result as a .txt file.

POST /download  with kind (which tool) and content (the result text).

Why the browser sends the text back instead of the server re-running the
tool: the tools are random, so running them again would give DIFFERENT
addresses from the ones on screen. Echoing back what's shown guarantees the
file matches the page.
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from app.web.forms import read_large_form

router = APIRouter()

# The file name for each tool. Only these names are ever used, so nothing
# typed into a form can choose the file name.
FILE_NAMES = {
    "ip": "ip-addresses.txt",
    "mac": "mac-addresses.txt",
    "convert-colon": "mac-colon.txt",
    "convert-hyphen": "mac-hyphen.txt",
    "convert-dotted": "mac-dotted.txt",
    "hosts": "fake-hostnames.txt",
    "oui-vendors": "mac-vendors.txt",
    "oui-prefixes": "vendor-prefixes.txt",
    "subnets": "subnets.txt",
    "iplist-summary": "ip-summary.txt",
    "iplist-sorted": "ip-sorted.txt",
    "iplist-original": "ip-unique.txt",
    "vlan-compressed": "vlans-compressed.txt",
    "vlan-expanded": "vlans.txt",
}

# Results whose blank lines matter: the hostname faker's and the OUI lookup's
# output line up row for row with a spreadsheet column, so an empty row must
# stay empty.
KEEP_BLANK_LINES = {"hosts", "oui-vendors"}


@router.post("/download")
async def download(request: Request):
    # A full /16 of results is about 2 MB, over Starlette's usual 1 MB limit
    # per field, so the form is read with a larger limit (see read_large_form).
    data = await read_large_form(request)
    kind = data.get("kind", "")
    file_name = FILE_NAMES.get(kind)
    if file_name is None:
        return PlainTextResponse("Unknown download.", status_code=400)

    # Windows line endings (CRLF), so the file looks right in any Windows
    # editor; Linux editors handle them fine too. Blank lines are dropped,
    # except for results where they mark a row (KEEP_BLANK_LINES).
    lines = data.get("content", "").splitlines()
    if kind not in KEEP_BLANK_LINES:
        lines = [line for line in lines if line.strip()]
    body = "\r\n".join(lines) + "\r\n" if lines else ""
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        # "attachment" tells the browser to save the file instead of showing it.
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
