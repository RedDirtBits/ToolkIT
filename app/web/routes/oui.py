"""
oui.py — the OUI lookup tab: who made this MAC, and the reverse.

POST /oui/lookup  with macs (one or many, any format, or bare prefixes)
                  -> the vendor of each, in a table, plus a "Vendors" box with
                  one vendor per line in the same order (a spreadsheet column).
POST /oui/search  with vendor (part of a name), style, upper
                  -> every block registered to matching vendors, plus a
                  "Prefixes" box ready to copy into a MAC filter or ACL.
POST /oui/update  -> download the latest list from IEEE (the ONLY network
                  access in ToolkIT, and only when this button is clicked).
POST /oui/import  with file -> save a list downloaded in the browser.

Update and Import answer with the "IEEE list" panel (_oui_status.html),
which htmx swaps in place of the old one. The work is done by
app/tools/oui_data.py and oui_update.py; the list in memory lives in
app/web/oui_state.py.
"""

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile

from app import settings
from app.tools.limits import MAX_ITEMS
from app.tools.oui_data import OUIDataError, lookup_lines
from app.tools.oui_update import MAX_FILE_BYTES, OUIUpdateError, import_file, update_from_ieee
from app.web.forms import is_checked, read_large_form
from app.web.responses import OutputBlock, Table, ToolResult, tool_response
from app.web.templating import render

router = APIRouter()

NO_LIST = "There's no vendor list yet. Click Update below to download it from IEEE (or Import a file)."


@router.post("/oui/lookup")
async def lookup(request: Request):
    # Read by hand so a big paste (over 1 MB) is accepted, as in the converter.
    data = await read_large_form(request)
    macs = data.get("macs", "")
    form = {"macs": macs}

    def refuse(message: str):
        return tool_response(request, ToolResult(kind="oui_lookup", tab="oui", error=message), form)

    db = request.app.state.oui.db
    if db is None:
        # No files yet, or files that couldn't be read (oui_state.py says why).
        return refuse(request.app.state.oui.error or NO_LIST)
    if not macs.strip():
        return refuse("Type or paste a MAC address (or a prefix like 00:1a:2b).")
    if len(macs.splitlines()) > MAX_ITEMS:
        return refuse(f"That's more than {MAX_ITEMS:,} lines; look them up in parts.")

    results = lookup_lines(macs, db)
    found = [r for r in results if r is not None]

    if len(found) == 1:
        # The usual case: one MAC. The answer goes in the summary line, big and plain.
        (only,) = found
        summary = only.label
    else:
        vendors = sum(1 for r in found if r.kind == "vendor")
        summary = f"{len(found):,} looked up: {vendors:,} with a vendor"
        others = len(found) - vendors
        if others:
            summary += f", {others:,} other (see the table)"

    rows = [
        [
            r.text,
            r.label,
            r.assignment.block if r.assignment else "",
            r.assignment.format_prefix() if r.assignment else "",
        ]
        for r in found[: settings.MAX_TABLE_ROWS]
    ]
    note = (
        f"First {settings.MAX_TABLE_ROWS:,} of {len(found):,} shown; the Vendors box has them all."
        if len(found) > settings.MAX_TABLE_ROWS
        else ""
    )
    table = Table(headers=["MAC", "Vendor", "Block", "Prefix"], rows=rows, note=note)

    blocks = []
    if len(found) > 1:
        # One vendor per input line, blank lines kept, to paste beside a column of MACs.
        lines = [r.label if r else "" for r in results]
        blocks = [OutputBlock(download="oui-vendors", lines=lines, title="Vendors, one per line")]

    result = ToolResult(kind="oui_lookup", tab="oui", summary=summary, table=table, blocks=blocks)
    return tool_response(request, result, form)


@router.post("/oui/search")
async def search(request: Request):
    data = await read_large_form(request)
    vendor = data.get("vendor", "")
    style = data.get("style", "colon")
    upper = data.get("upper", "")
    form = {"vendor": vendor, "style": style, "upper": upper}

    def refuse(message: str):
        return tool_response(request, ToolResult(kind="oui_search", tab="oui", error=message), form)

    db = request.app.state.oui.db
    if db is None:
        # No files yet, or files that couldn't be read (oui_state.py says why).
        return refuse(request.app.state.oui.error or NO_LIST)
    try:
        matches = db.search(vendor)
    except OUIDataError as error:
        return refuse(str(error))
    if not matches:
        return refuse(f"No vendor name contains '{vendor.strip()}'. Try a shorter part of the name.")

    upper_flag = is_checked(upper)
    prefixes = [entry.format_prefix(style, upper_flag) for entry in matches]
    names = sorted({entry.vendor for entry in matches})
    summary = (
        f"{len(matches):,} {_plural(len(matches), 'block')} registered to "
        f"{len(names):,} matching vendor {_plural(len(names), 'name')}"
    )

    rows = [[p, e.block, e.vendor] for p, e in zip(prefixes, matches)][: settings.MAX_TABLE_ROWS]
    note = (
        f"First {settings.MAX_TABLE_ROWS:,} of {len(matches):,} shown; the Prefixes box has them all."
        if len(matches) > settings.MAX_TABLE_ROWS
        else ""
    )
    result = ToolResult(
        kind="oui_search",
        tab="oui",
        summary=summary,
        table=Table(headers=["Prefix", "Block", "Vendor"], rows=rows, note=note),
        blocks=[OutputBlock(download="oui-prefixes", lines=prefixes, title="Prefixes")],
        # More than one name usually means unrelated companies matched too: say which.
        warnings=[f"Matched names: {'; '.join(names)}"] if len(names) > 1 else [],
    )
    return tool_response(request, result, form)


@router.post("/oui/update")
def update(request: Request):
    state = request.app.state.oui
    try:
        counts = update_from_ieee(state.folder, fetch=state.fetch)
    except OUIUpdateError as error:
        return _status_response(request, error=str(error))
    state.reload()
    return _status_response(request, message=f"Updated from IEEE: {sum(counts.values()):,} entries.")


@router.post("/oui/import")
async def import_(request: Request):
    # A file upload. Starlette keeps the file on disk while it arrives; we read
    # at most one byte past the size limit, so a huge file can't fill memory.
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or not upload.filename:
        return _status_response(request, error="Choose a file first (oui.csv, mam.csv or oui36.csv).")
    data = await upload.read(MAX_FILE_BYTES + 1)
    state = request.app.state.oui
    try:
        block, count = import_file(state.folder, data)
    except OUIUpdateError as error:
        return _status_response(request, error=str(error))
    state.reload()
    return _status_response(request, message=f"Imported the {block} list: {count:,} entries.")


def _plural(count: int, word: str) -> str:
    """'block' for 1, 'blocks' otherwise."""
    return word if count == 1 else word + "s"


def _status_response(request: Request, message: str = "", error: str = ""):
    """The refreshed "IEEE list" panel for htmx, or the whole page (OUI tab) without JavaScript."""
    context = {"oui_message": message, "oui_error": error}
    if request.headers.get("HX-Request") == "true":
        return render(request, "_oui_status.html", **context)
    return render(request, "index.html", tab="oui", **context)
