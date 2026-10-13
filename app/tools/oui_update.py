"""Fetch IEEE's MAC registries (Update button) or take a copy the user downloaded (Import button).

This is the ONLY code in ToolkIT that uses the network, and it runs only when the user clicks
Update. Everything else, lookups included, works offline from the saved files.

Both paths end the same way: the file is checked with oui_data.parse_registry_csv() BEFORE it's
saved, then saved with an "atomic replace": written to a temporary file next to the real one, then
renamed over it in one step. If anything goes wrong halfway (no network, a bad file, the laptop
going to sleep), the old list is still there, whole. Think of it as writing a new page on a separate
sheet and only swapping it in once it's finished, rather than erasing and rewriting the page itself.
That protects each FILE. The three files of an Update are swapped in one after another, so if the
disk refuses the second one, the first is already new (the message says so; see update_from_ieee).

No web code: the web layer calls these and reloads its in-memory list afterwards.
"""

from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.tools.oui_data import BLOCKS, OUIDataError, parse_registry_csv

# Where each block's file lives on IEEE's site. Fixed addresses, refreshed by IEEE daily.
IEEE_URLS = {
    "MA-L": "https://standards-oui.ieee.org/oui/oui.csv",
    "MA-M": "https://standards-oui.ieee.org/oui28/mam.csv",
    "MA-S": "https://standards-oui.ieee.org/oui36/oui36.csv",
}

# IEEE turns away Python's default User-Agent ("Python-urllib/3.x") with HTTP 418, so we say who
# we are instead. (A User-Agent is the name a program gives a web server when it asks for a page.)
USER_AGENT = "ToolkIT/1.0 (offline OUI lookup)"

# Seconds to wait for IEEE before giving up, per file.
TIMEOUT = 60

# The biggest file accepted, from IEEE or an import. The real ones are under 4 MB; this stops a
# wrong file (or a broken server) from filling memory.
MAX_FILE_BYTES = 50 * 1024 * 1024

# A "fetcher" takes a URL and returns the file's bytes. The real one uses the network; tests pass
# a fake one, so they never touch the internet (this is called dependency injection).
Fetcher = Callable[[str], bytes]


class OUIUpdateError(ValueError):
    """An update or import that didn't work. The message is safe to show the user."""


def fetch_url(url: str) -> bytes:
    """Download one file. urllib uses the system's proxy settings (on Windows, the same ones the
    browser is set to), unless the proxy needs a login or a setup script."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        # Read one byte past the limit: if we get it, the file is too big.
        data = response.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OUIUpdateError(f"{url} is larger than expected; not saved.")
    return data


def update_from_ieee(folder: Path, fetch: Fetcher = fetch_url) -> dict[str, int]:
    """Download all three registries and save them. Returns entries per block.

    All three are downloaded and checked first; only then is anything saved. So a failed DOWNLOAD
    of the second file leaves all the old files alone, rather than a mix of old and new.
    """
    checked: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    for block, url in IEEE_URLS.items():
        try:
            data = fetch(url)
        except urllib.error.HTTPError as error:
            raise OUIUpdateError(f"IEEE refused the download of {url} (HTTP {error.code}).") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # URLError covers "no network", "name not found" and proxy failures.
            reason = getattr(error, "reason", error)
            raise OUIUpdateError(
                f"Couldn't reach IEEE ({reason}). If this network uses a proxy that needs a login, "
                "download the files in your browser and use Import instead."
            ) from None
        found_block, entries = _check(data, url)
        if found_block != block:
            raise OUIUpdateError(f"{url} held the {found_block} list instead of {block}; not saved.")
        checked[block] = data
        counts[block] = len(entries)

    # Saving is one file at a time, not all-or-nothing (decided 2026-10-12: a failed save is rare,
    # a part-new part-old list still works, and Update again repairs it). So if a later save
    # fails, say that the earlier ones did go through.
    saved: list[str] = []
    for block, data in checked.items():
        file_name = BLOCKS[block][0]
        try:
            _save(folder, file_name, data)
        except OUIUpdateError as error:
            if saved:
                raise OUIUpdateError(
                    f"{error} {', '.join(saved)} {'was' if len(saved) == 1 else 'were'} already "
                    "updated; the list still works, and Update again will finish the job."
                ) from None
            raise
        saved.append(file_name)
    return counts


def import_file(folder: Path, data: bytes) -> tuple[str, int]:
    """Save a registry file the user downloaded themselves. Returns its block and entry count.

    Which of the three it is (oui.csv, mam.csv or oui36.csv) is read from the file itself, so
    the user doesn't have to say, and a renamed file still lands in the right place.
    """
    if len(data) > MAX_FILE_BYTES:
        raise OUIUpdateError("That file is far larger than an IEEE registry file; not imported.")
    block, entries = _check(data, "That file")
    _save(folder, BLOCKS[block][0], data)
    return block, len(entries)


def file_dates(folder: Path) -> dict[str, datetime | None]:
    """When each block's file was last saved (None if missing), for "List from ..." on the page."""
    dates: dict[str, datetime | None] = {}
    for block, (file_name, _) in BLOCKS.items():
        path = folder / file_name
        dates[block] = datetime.fromtimestamp(path.stat().st_mtime) if path.is_file() else None
    return dates


def _check(data: bytes, source: str) -> tuple[str, list]:
    """Decode and validate a registry file before it's saved. Returns parse_registry_csv()'s result."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise OUIUpdateError(f"{source} isn't a text (UTF-8) file, so it isn't an IEEE list.") from None
    try:
        return parse_registry_csv(text)
    except OUIDataError as error:
        raise OUIUpdateError(f"{source}: {error}") from None


def _save(folder: Path, file_name: str, data: bytes) -> None:
    """Write `data` to folder/file_name with an atomic replace (see the module docstring).

    A save can fail for reasons outside the app: a read-only or full disk, a folder the user may
    not write to, or (on Windows) antivirus holding the file open. Python reports all of these as
    OSError. The web page only knows how to show OUIUpdateError, so the error is turned into one
    that names the folder and the reason; otherwise the user would click Update and see nothing.
    """
    try:
        _write_atomically(folder, file_name, data)
    except OSError as error:
        # strerror is the plain reason ("Permission denied", "No space left on device").
        reason = error.strerror or str(error)
        raise OUIUpdateError(
            f"Couldn't save {file_name} in {folder} ({reason}). The old file is unchanged."
        ) from None


def _write_atomically(folder: Path, file_name: str, data: bytes) -> None:
    """The write itself: a temporary file in the same folder, then one rename over the real file."""
    folder.mkdir(parents=True, exist_ok=True)
    # mkstemp creates a new, uniquely named temporary file in the same folder (the same folder
    # matters: a rename is only one atomic step within one disk).
    handle, temp_name = tempfile.mkstemp(dir=folder, prefix=f".{file_name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as temp_file:
            temp_file.write(data)
        # os.replace swaps the new file in, replacing the old one if there is one, in one step,
        # on Linux and Windows alike.
        os.replace(temp_path, folder / file_name)
    except BaseException:
        # Anything went wrong: remove the half-written temporary file, keep the old list.
        temp_path.unlink(missing_ok=True)
        raise
