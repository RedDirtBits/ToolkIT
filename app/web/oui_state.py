"""
oui_state.py — the OUI list the running app looks things up in.

Reading IEEE's three files takes about a quarter of a second, far too slow
to repeat for every lookup. So the list is read once, on first use, and kept
in memory here. After an Update or Import, reload() reads the new files.

One OUIState lives on the app (app.state.oui, set up in main.py), and the
routes reach it through request.app.state.oui. Tests build the app with
their own folder and a fake downloader, so they never use the network.

It "fails soft": a missing, unreadable or broken file never raises from
here. It becomes a status the OUI tab shows ("couldn't be read: <reason>;
Update or Import to replace it"), so the other seven tabs, which never use
the list, keep working. Like a fuse that cuts one room's lights, not the
whole house.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.tools.oui_data import OUIDatabase, OUIDataError, load_folder
from app.tools.oui_update import Fetcher, fetch_url, file_dates


@dataclass(frozen=True)
class OUIStatus:
    """What the page shows about the list: is there one, how big, how old."""

    loaded: bool
    total: int = 0
    counts: dict[str, int] | None = None
    # The OLDEST of the files' dates: the list is only as fresh as its stalest part.
    list_date: datetime | None = None
    # Why the files couldn't be read, when they couldn't (shown instead of "No list yet").
    error: str = ""


class OUIState:
    def __init__(self, folder: Path, fetch: Fetcher = fetch_url) -> None:
        self.folder = folder
        self.fetch = fetch  # how Update downloads; tests swap in a fake
        self._db: OUIDatabase | None = None
        self._loaded = False  # True once we've looked, even if no files were there
        self.error = ""  # set by reload() when the files are there but can't be read

    @property
    def db(self) -> OUIDatabase | None:
        """The list, read from disk the first time it's asked for. None if there are no files."""
        if not self._loaded:
            self.reload()
        return self._db

    def reload(self) -> None:
        """Read the files again (after an Update or Import). Never raises: see the module docstring."""
        # Build the new list completely before swapping it in, so a lookup running at the same
        # moment sees either the whole old list or the whole new one.
        try:
            db = load_folder(self.folder)
        except (OSError, UnicodeDecodeError, OUIDataError) as error:
            # OSError: a file locked or not readable. UnicodeDecodeError: not a text file.
            # OUIDataError: text, but not an IEEE list (e.g. a wrong file copied in by hand).
            # Without a usable list, lookups say why instead of answering from a broken one.
            self._db = None
            self.error = (
                f"The vendor list in {self.folder} couldn't be read ({_reason(error)}). "
                "Click Update from IEEE, or Import the files, to replace it."
            )
        else:
            self._db = db
            self.error = ""
        self._loaded = True

    def status(self) -> OUIStatus:
        db = self.db
        if db is None:
            return OUIStatus(loaded=False, error=self.error)
        try:
            dates = [d for d in file_dates(self.folder).values() if d is not None]
        except OSError:
            dates = []
        if not dates:
            # The files were there when the list was read, but are gone now (e.g. data/oui/
            # deleted while the app runs). Say "no list", so the user is told to click Update.
            return OUIStatus(loaded=False)
        return OUIStatus(loaded=True, total=len(db), counts=db.counts(), list_date=min(dates))


def _reason(error: Exception) -> str:
    """A short reason for an error: strerror for file errors ("Permission denied"), else the message."""
    return getattr(error, "strerror", None) or str(error)
