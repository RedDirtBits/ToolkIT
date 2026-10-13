"""Tests for the VLAN list tab (the engine itself is tested in test_vlan_list.py). Invented VLANs."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.web.oui_state import OUIState

HTMX = {"HX-Request": "true"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(allowed_hosts={"testserver"}, oui_state=OUIState(tmp_path)))


def box(html: str, kind: str) -> list[str]:
    start = html.index(f'id="{kind}-output"')
    body = html[html.index(">", start) + 1 : html.index("</textarea>", start)]
    return body.removeprefix("\n").split("\n")


def test_compress_and_expand_at_once(client):
    response = client.post("/vlan", data={"vlans": "100 23 22\n21 20 10 10"}, headers=HTMX)
    assert box(response.text, "vlan-compressed") == ["10,20-23,100"]
    assert box(response.text, "vlan-expanded") == ["10", "20", "21", "22", "23", "100"]
    assert "6 VLANs, 85 free between 10 and 100" in response.text
    assert box(response.text, "vlan-free") == ["11-19,24-99"]


def test_skipped_items_are_listed(client):
    response = client.post("/vlan", data={"vlans": "UPLINK 1/1/1 7 8 9 5000"}, headers=HTMX)
    assert box(response.text, "vlan-compressed") == ["7-9"]
    assert "3 VLANs, 0 free between 7 and 9, 3 items skipped" in response.text
    assert "vlan-free-output" not in response.text  # no gaps, no box
    assert "Skipped &#39;1/1/1&#39;: not a VLAN number or range" in response.text
    assert "Skipped &#39;5000&#39;: outside 1-4094" in response.text


def test_a_huge_number_is_skipped_not_a_crash(client):
    # 5,000 digits is past Python's int() limit (4,300): before the fix this was a 500.
    response = client.post("/vlan", data={"vlans": "7 " + "9" * 5000 + " 8"}, headers=HTMX)
    assert response.status_code == 200
    assert box(response.text, "vlan-compressed") == ["7-8"]
    assert "1 item skipped" in response.text
    assert "not a VLAN number or range" in response.text


def test_nothing_valid(client):
    response = client.post("/vlan", data={"vlans": "trunk smlt"}, headers=HTMX)
    assert "Nothing valid found" in response.text
    assert "vlan-compressed-output" not in response.text


def test_empty_paste_is_refused(client):
    assert "Paste some VLANs" in client.post("/vlan", data={"vlans": " "}, headers=HTMX).text


def test_without_javascript_returns_the_vlan_tab(client):
    response = client.post("/vlan", data={"vlans": "10,20-23"})
    assert 'id="tab-vlan" class="tab-radio" checked' in response.text
    assert "10,20-23" in response.text


def test_input_is_escaped(client):
    response = client.post("/vlan", data={"vlans": "<script>x</script>"}, headers=HTMX)
    assert "<script>" not in response.text


@pytest.mark.parametrize(
    "kind, name",
    [
        ("vlan-compressed", "vlans-compressed.txt"),
        ("vlan-expanded", "vlans.txt"),
        ("vlan-free", "vlans-free.txt"),
    ],
)
def test_download_names(client, kind, name):
    response = client.post("/download", data={"kind": kind, "content": "10"})
    assert f'filename="{name}"' in response.headers["content-disposition"]


def test_compressed_view_wraps_only_after_commas(client):
    response = client.post("/vlan", data={"vlans": "5 7 8 9 20"}, headers=HTMX)
    assert (
        '<div class="output wrapped-view"><span class="nowrap">5</span>,<wbr>'
        '<span class="nowrap">7-9</span>,<wbr><span class="nowrap">20</span></div>'
    ) in response.text
    # The exact one-line text is still there for Copy and Download.
    assert box(response.text, "vlan-compressed") == ["5,7-9,20"]


def test_wrap_after_commas_escapes_each_item():
    from app.web.templating import wrap_after_commas

    assert (
        str(wrap_after_commas("<b>,7"))
        == '<span class="nowrap">&lt;b&gt;</span>,<wbr><span class="nowrap">7</span>'
    )
