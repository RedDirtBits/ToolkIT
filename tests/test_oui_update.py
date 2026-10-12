"""Tests for app/tools/oui_update.py.

No test touches the internet: update_from_ieee() is given a fake "fetcher" that returns the small
fixture files (or fails on purpose). Files are written to pytest's tmp_path, a fresh empty folder
per test.
"""

import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from app.tools.oui_data import load_folder
from app.tools.oui_update import (
    IEEE_URLS,
    MAX_FILE_BYTES,
    USER_AGENT,
    OUIUpdateError,
    file_dates,
    import_file,
    update_from_ieee,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ieee"

# URL -> the fixture file standing in for it.
FAKE_FILES = {
    IEEE_URLS["MA-L"]: FIXTURES / "oui.csv",
    IEEE_URLS["MA-M"]: FIXTURES / "mam.csv",
    IEEE_URLS["MA-S"]: FIXTURES / "oui36.csv",
}


def fake_fetch(url: str) -> bytes:
    return FAKE_FILES[url].read_bytes()


# --- update_from_ieee ----------------------------------------------------------------------------


def test_update_saves_all_three_files(tmp_path):
    folder = tmp_path / "data" / "oui"  # doesn't exist yet: update must create it
    counts = update_from_ieee(folder, fetch=fake_fetch)
    assert counts == {"MA-L": 8, "MA-M": 2, "MA-S": 1}
    assert sorted(p.name for p in folder.iterdir()) == ["mam.csv", "oui.csv", "oui36.csv"]
    database = load_folder(folder)
    assert database is not None
    assert database.counts() == {"MA-S": 1, "MA-M": 2, "MA-L": 8}


def test_failed_download_keeps_the_old_files(tmp_path):
    update_from_ieee(tmp_path, fetch=fake_fetch)
    before = (tmp_path / "oui.csv").read_bytes()

    def failing_fetch(url):
        if url == IEEE_URLS["MA-M"]:  # the second of three files
            raise urllib.error.URLError("proxy said no")
        return b"Registry,Assignment,Organization Name,Organization Address\nMA-L,AAAAAA,New,\n"

    with pytest.raises(OUIUpdateError, match="Couldn't reach IEEE .*proxy said no.*Import"):
        update_from_ieee(tmp_path, fetch=failing_fetch)
    # Nothing was saved, not even the first file that downloaded fine.
    assert (tmp_path / "oui.csv").read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_http_error_is_explained(tmp_path):
    def refusing_fetch(url):
        # Message() = empty HTTP headers (the type urllib uses for them).
        raise urllib.error.HTTPError(url, 418, "I'm a teapot", Message(), None)

    with pytest.raises(OUIUpdateError, match="HTTP 418"):
        update_from_ieee(tmp_path, fetch=refusing_fetch)


def test_garbage_from_the_server_is_not_saved(tmp_path):
    with pytest.raises(OUIUpdateError, match="isn't an IEEE registry CSV"):
        update_from_ieee(tmp_path, fetch=lambda url: b"<html>Access denied</html>")
    assert not any(tmp_path.iterdir())


def test_wrong_list_at_a_url_is_not_saved(tmp_path):
    # Every URL returns the MA-L file: the MA-M one must be refused.
    with pytest.raises(OUIUpdateError, match="held the MA-L list instead of MA-M"):
        update_from_ieee(tmp_path, fetch=lambda url: FAKE_FILES[IEEE_URLS["MA-L"]].read_bytes())


def test_the_real_fetcher_sends_our_user_agent(monkeypatch):
    # Catch the request instead of sending it, and check its User-Agent header.
    seen = {}

    def fake_urlopen(request, timeout):
        seen["agent"] = request.get_header("User-agent")
        raise urllib.error.URLError("not really sending")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(OUIUpdateError):
        update_from_ieee(Path("unused"))
    assert seen["agent"] == USER_AGENT


# --- import_file ---------------------------------------------------------------------------------


def test_import_detects_which_file_it_is(tmp_path):
    block, count = import_file(tmp_path, (FIXTURES / "mam.csv").read_bytes())
    assert (block, count) == ("MA-M", 2)
    assert (tmp_path / "mam.csv").read_bytes() == (FIXTURES / "mam.csv").read_bytes()


def test_import_replaces_an_older_copy(tmp_path):
    (tmp_path / "oui36.csv").write_text("old")
    import_file(tmp_path, (FIXTURES / "oui36.csv").read_bytes())
    database = load_folder(tmp_path)
    assert database is not None
    assert database.counts()["MA-S"] == 1


@pytest.mark.parametrize(
    "data, message",
    [
        (b"\xff\xfe\x00binary", "isn't a text"),
        (b"name,email\nx,y\n", "isn't an IEEE registry CSV"),
    ],
)
def test_import_refuses_other_files(tmp_path, data, message):
    with pytest.raises(OUIUpdateError, match=message):
        import_file(tmp_path, data)
    assert not any(tmp_path.iterdir())


def test_import_refuses_huge_files(tmp_path):
    with pytest.raises(OUIUpdateError, match="far larger"):
        import_file(tmp_path, b"x" * (MAX_FILE_BYTES + 1))


# --- file_dates ----------------------------------------------------------------------------------


def test_file_dates(tmp_path):
    assert file_dates(tmp_path) == {"MA-S": None, "MA-M": None, "MA-L": None}
    import_file(tmp_path, (FIXTURES / "oui.csv").read_bytes())
    dates = file_dates(tmp_path)
    assert dates["MA-L"] is not None and dates["MA-M"] is None
