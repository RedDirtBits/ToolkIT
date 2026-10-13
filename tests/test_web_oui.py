"""Tests for the OUI lookup tab: lookups, vendor search, Update and Import.

The app is built with an OUIState pointing at a temporary folder and a fake downloader, so no test
uses the real list or the network. The fake registry files are in tests/fixtures/ieee/.
"""

import shutil
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tools.oui_update import IEEE_URLS
from app.web.oui_state import OUIState

FIXTURES = Path(__file__).parent / "fixtures" / "ieee"
HTMX = {"HX-Request": "true"}
FAKE_FILES = {
    IEEE_URLS["MA-L"]: FIXTURES / "oui.csv",
    IEEE_URLS["MA-M"]: FIXTURES / "mam.csv",
    IEEE_URLS["MA-S"]: FIXTURES / "oui36.csv",
}


def fake_fetch(url: str) -> bytes:
    return FAKE_FILES[url].read_bytes()


def make_client(folder: Path, fetch=fake_fetch) -> TestClient:
    return TestClient(create_app(allowed_hosts={"testserver"}, oui_state=OUIState(folder, fetch)))


@pytest.fixture
def client(tmp_path):
    """An app whose list is a copy of the fake fixture files."""
    shutil.copytree(FIXTURES, tmp_path / "oui")
    return make_client(tmp_path / "oui")


@pytest.fixture
def empty_client(tmp_path):
    """An app with no list yet (first run)."""
    return make_client(tmp_path / "oui")


def textarea_lines(html: str, box: str) -> list[str]:
    """The lines of an output box, read as a browser does (first newline after the tag dropped)."""
    start = html.index(f'id="{box}"')
    body = html[html.index(">", start) + 1 : html.index("</textarea>", start)]
    return body.removeprefix("\n").split("\n")


# --- the page ------------------------------------------------------------------------------------


def test_tab_shows_list_status(client):
    page = client.get("/?tab=oui").text
    assert 'id="tab-oui" class="tab-radio" checked' in page
    assert "11 entries" in page and "list from" in page


def test_first_run_says_there_is_no_list(empty_client):
    page = empty_client.get("/?tab=oui").text
    assert "No list yet" in page


def test_both_forms_have_clear_buttons_and_own_results(client):
    page = client.get("/?tab=oui").text
    for name in ("lookup", "search"):
        form = page[page.index(f'action="/oui/{name}"') : page.index(f'id="oui-{name}-result"')]
        assert '<button type="reset" class="secondary">Clear</button>' in form
        assert f'data-result="oui-{name}-result"' in form


# --- lookup --------------------------------------------------------------------------------------


def test_single_lookup_puts_the_vendor_in_the_summary(client):
    response = client.post("/oui/lookup", data={"macs": "001a.2b3c.4d5e"}, headers=HTMX)
    assert '<p class="summary">Example Networks, Inc.</p>' in response.text
    assert "<td>MA-L</td>" in response.text and "<td>00:1a:2b</td>" in response.text
    assert "oui-vendors-output" not in response.text  # no column box for a single MAC


def test_many_lookups_give_a_vendor_column(client):
    pasted = "00:1a:2b:00:00:01\n\n02:00:00:00:00:01\nnonsense\n"
    response = client.post("/oui/lookup", data={"macs": pasted}, headers=HTMX)
    assert textarea_lines(response.text, "oui-vendors-output") == [
        "Example Networks, Inc.",
        "",
        "Locally administered (randomized or set by software; no vendor)",
        "(not a MAC address)",
    ]
    assert "3 looked up: 1 with a vendor, 2 other" in response.text


def test_lookup_without_a_list_explains(empty_client):
    response = empty_client.post("/oui/lookup", data={"macs": "00:1a:2b"}, headers=HTMX)
    assert "no vendor list yet" in response.text


def test_empty_lookup_is_refused(client):
    response = client.post("/oui/lookup", data={"macs": "  "}, headers=HTMX)
    assert "Type or paste a MAC" in response.text


def test_lookup_without_javascript_returns_the_oui_tab(client):
    response = client.post("/oui/lookup", data={"macs": "00:1a:2b"})
    assert 'id="tab-oui" class="tab-radio" checked' in response.text
    assert '<p class="summary">Example Networks, Inc.</p>' in response.text


def test_lookup_input_is_escaped(client):
    response = client.post("/oui/lookup", data={"macs": "<script>x</script>"}, headers=HTMX)
    assert "<script>" not in response.text


# --- vendor search -------------------------------------------------------------------------------


def test_search_lists_prefixes_in_the_chosen_format(client):
    data = {"vendor": "tiny sensors", "style": "hyphen", "upper": "on"}
    response = client.post("/oui/search", data=data, headers=HTMX)
    assert textarea_lines(response.text, "oui-prefixes-output") == ["BC-56-78-01-A0-00/36"]
    assert "1 block registered to 1 matching vendor name" in response.text


def test_search_names_every_matching_vendor(client):
    response = client.post("/oui/search", data={"vendor": "example networks"}, headers=HTMX)
    assert textarea_lines(response.text, "oui-prefixes-output") == ["00:e0:f1", "00:1a:2b"]
    assert "Matched names: Example Networks Labs; Example Networks, Inc." in response.text


@pytest.mark.parametrize(
    "vendor, message",
    [("x", "at least 2"), ("no such vendor", "No vendor name contains")],
)
def test_search_errors(client, vendor, message):
    response = client.post("/oui/search", data={"vendor": vendor}, headers=HTMX)
    assert message in response.text


# --- update and import ---------------------------------------------------------------------------


def test_update_downloads_and_reloads(empty_client):
    response = empty_client.post("/oui/update", headers=HTMX)
    assert "Updated from IEEE: 11 entries" in response.text
    assert 'id="oui-status"' in response.text
    # The new list is used straight away.
    lookup = empty_client.post("/oui/lookup", data={"macs": "00:1a:2b"}, headers=HTMX)
    assert "Example Networks, Inc." in lookup.text


def test_failed_update_is_explained(tmp_path):
    def offline(url):
        raise urllib.error.URLError("no route to host")

    response = make_client(tmp_path, fetch=offline).post("/oui/update", headers=HTMX)
    assert "Couldn&#39;t reach IEEE" in response.text and "Import" in response.text


def test_import_a_file(empty_client):
    files = {"file": ("mam.csv", (FIXTURES / "mam.csv").read_bytes(), "text/csv")}
    response = empty_client.post("/oui/import", files=files, headers=HTMX)
    assert "Imported the MA-M list: 2 entries" in response.text
    assert "2 entries" in response.text


def test_import_refuses_other_files(empty_client):
    files = {"file": ("people.csv", b"name,email\nx,y\n", "text/csv")}
    response = empty_client.post("/oui/import", files=files, headers=HTMX)
    assert "isn&#39;t an IEEE registry CSV" in response.text


def test_import_without_a_file(empty_client):
    response = empty_client.post("/oui/import", data={}, headers=HTMX)
    assert "Choose a file first" in response.text


def test_failed_save_is_explained(tmp_path):
    # A file where the data/oui folder should be: the download works, the save can't.
    folder = tmp_path / "oui"
    folder.write_text("not a folder")
    response = make_client(folder).post("/oui/update", headers=HTMX)
    assert response.status_code == 200
    assert "Couldn&#39;t save oui.csv" in response.text and 'id="oui-status"' in response.text


# --- a broken or vanished list doesn't take the other tabs down (review finding 1) ----------------


@pytest.mark.parametrize(
    "content",
    [
        b"name,email\nx,y\n",  # text, but not an IEEE list (a wrong file copied in by hand)
        b"\xff\xfe\x00binary",  # not text at all
    ],
)
def test_unreadable_list_is_a_status_not_a_crash(tmp_path, content):
    shutil.copytree(FIXTURES, tmp_path / "oui")
    (tmp_path / "oui" / "oui.csv").write_bytes(content)
    client = make_client(tmp_path / "oui")

    # Other tabs work as usual.
    assert client.get("/").status_code == 200
    vlan = client.post("/vlan", data={"vlans": "10 11 12"}, headers=HTMX)
    assert vlan.status_code == 200 and "10-12" in vlan.text
    # The OUI tab says what's wrong and what to do.
    page = client.get("/?tab=oui").text
    assert "couldn&#39;t be read" in page and "Update from IEEE" in page
    lookup = client.post("/oui/lookup", data={"macs": "00:1a:2b"}, headers=HTMX)
    assert lookup.status_code == 200 and "couldn&#39;t be read" in lookup.text
    # Update replaces the broken file, and the list works again.
    assert "Updated from IEEE" in client.post("/oui/update", headers=HTMX).text
    lookup = client.post("/oui/lookup", data={"macs": "00:1a:2b"}, headers=HTMX)
    assert "Example Networks, Inc." in lookup.text


def test_list_deleted_while_running(tmp_path):
    # The README's old Recover step: delete data/oui/ while the app runs.
    shutil.copytree(FIXTURES, tmp_path / "oui")
    client = make_client(tmp_path / "oui")
    assert "11 entries" in client.get("/?tab=oui").text  # the list is read and in memory
    shutil.rmtree(tmp_path / "oui")

    assert client.get("/").status_code == 200
    assert client.post("/vlan", data={"vlans": "10"}, headers=HTMX).status_code == 200
    assert "No list yet" in client.get("/?tab=oui").text
    # Update brings it back.
    assert "Updated from IEEE: 11 entries" in client.post("/oui/update", headers=HTMX).text


def test_update_from_another_site_is_refused(empty_client):
    response = empty_client.post("/oui/update", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403


def test_vendor_downloads_keep_blank_lines(client):
    response = client.post("/download", data={"kind": "oui-vendors", "content": "A\n\nB"})
    assert response.content == b"A\r\n\r\nB\r\n"
    assert 'filename="mac-vendors.txt"' in response.headers["content-disposition"]
