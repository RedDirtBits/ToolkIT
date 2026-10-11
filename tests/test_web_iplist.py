"""Tests for the IP list cleanup tab (the engine itself is tested in test_ip_list.py)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.web.oui_state import OUIState

HTMX = {"HX-Request": "true"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(allowed_hosts={"testserver"}, oui_state=OUIState(tmp_path)))


def box(html: str, kind: str) -> list[str]:
    """The lines of one output box, read as a browser does."""
    start = html.index(f'id="{kind}-output"')
    body = html[html.index(">", start) + 1 : html.index("</textarea>", start)]
    return body.removeprefix("\n").split("\n")


PASTE = "192.168.4.10\n192.168.4.2\n\n192.168.4.10\n192.168.5.0/24\nnonsense\n192.168.4.3"


def test_all_three_boxes_and_counts(client):
    response = client.post("/iplist", data={"ips": PASTE}, headers=HTMX)
    page = response.text
    assert box(page, "iplist-original") == ["192.168.4.10", "192.168.4.2", "192.168.5.0/24", "192.168.4.3"]
    assert box(page, "iplist-sorted") == ["192.168.4.2", "192.168.4.3", "192.168.4.10", "192.168.5.0/24"]
    assert box(page, "iplist-summary") == ["192.168.4.2/31", "192.168.4.10/32", "192.168.5.0/24"]
    assert "6 lines: 4 unique, 1 duplicate, 1 invalid → 3 blocks" in page
    assert "Line 6 skipped, not an address or network: nonsense" in page


def test_covering_block_shown_with_copy(client):
    response = client.post("/iplist", data={"ips": PASTE}, headers=HTMX)
    assert '<th scope="row">All fit in</th>' in response.text
    assert ">192.168.4.0/23</span>" in response.text
    assert 'data-copy="iplist-detail-1"' in response.text


def test_exact_fit_says_so(client):
    response = client.post("/iplist", data={"ips": "192.0.2.0/25\n192.0.2.128/25"}, headers=HTMX)
    assert box(response.text, "iplist-summary") == ["192.0.2.0/24"]
    assert "none: an exact fit" in response.text


def test_wildcard_style_for_acls(client):
    data = {"ips": "192.168.4.0/24\n192.168.5.0/24", "style": "wildcard"}
    response = client.post("/iplist", data=data, headers=HTMX)
    assert box(response.text, "iplist-summary") == ["192.168.4.0 0.0.1.255"]


def test_only_invalid_lines_shows_no_boxes(client):
    response = client.post("/iplist", data={"ips": "junk\nmore junk"}, headers=HTMX)
    assert "2 lines: 0 unique, 2 invalid" in response.text
    assert "iplist-summary-output" not in response.text


@pytest.mark.parametrize(
    "data, message",
    [({"ips": "  \n"}, "at least one"), ({"ips": "192.0.2.1", "style": "binary"}, "Unknown style")],
)
def test_errors_are_shown(client, data, message):
    assert message in client.post("/iplist", data=data, headers=HTMX).text


def test_without_javascript_returns_the_iplist_tab(client):
    response = client.post("/iplist", data={"ips": "192.0.2.1", "style": "mask"})
    assert 'id="tab-iplist" class="tab-radio" checked' in response.text
    assert '<option value="mask" selected' in response.text


def test_input_is_escaped(client):
    response = client.post("/iplist", data={"ips": "<script>x</script>"}, headers=HTMX)
    assert "<script>" not in response.text


@pytest.mark.parametrize(
    "kind, name",
    [("iplist-summary", "ip-summary.txt"), ("iplist-sorted", "ip-sorted.txt"), ("iplist-original", "ip-unique.txt")],
)
def test_download_names(client, kind, name):
    response = client.post("/download", data={"kind": kind, "content": "192.0.2.1"})
    assert f'filename="{name}"' in response.headers["content-disposition"]
