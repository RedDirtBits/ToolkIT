"""
oui_state.py — the OUI list the running app looks things up in.

Reading IEEE's three files takes about a quarter of a second, far too slow
to repeat for every lookup. So the list is read once, on first use, and kept
in memory here. After an Update or Import, reload() reads the new files.

One OUIState lives on the app (app.state.oui, set up in main.py), and the
routes reach it through request.app.state.oui. Tests build the app with
their own folder and a fake downloader, so they never use the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.tools.oui_data import OUIDatabase, load_folder
from app.tools.oui_update import Fetcher, fetch_url, file_dates


@dataclass(frozen=True)
class OUIStatus:
    """What the page shows about the list: is there one, how big, how old."""

    loaded: bool
    total: int = 0
    counts: dict[str, int] | None = None
    # The OLDEST of the files' dates: the list is only as fresh as its stalest part.
    list_date: datetime | None = None


class OUIState:
    def __init__(self, folder: Path, fetch: Fetcher = fetch_url) -> None:
        self.folder = folder
        self.fetch = fetch  # how Update downloads; tests swap in a fake
        self._db: OUIDatabase | None = None
        self._loaded = False  # True once we've looked, even if no files were there

    @property
    def db(self) -> OUIDatabase | None:
        """The list, read from disk the first time it's asked for. None if there are no files."""
        if not self._loaded:
            self.reload()
        return self._db

    def reload(self) -> None:
        """Read the files again (after an Update or Import)."""
        # Build the new list completely before swapping it in, so a lookup running at the same
        # moment sees either the whole old list or the whole new one.
        self._db = load_folder(self.folder)
        self._loaded = True

    def status(self) -> OUIStatus:
        db = self.db
        if db is None:
            return OUIStatus(loaded=False)
        dates = [d for d in file_dates(self.folder).values() if d is not None]
        return OUIStatus(loaded=True, total=len(db), counts=db.counts(), list_date=min(dates))
