"""Tests for the web layer: pages, the three tool forms, downloads and the local-only checks.

FastAPI's TestClient calls the app directly in memory, with no server or browser. It sends
"Host: testserver", so the app is built with that as its allowed host name.
"""

import ipaddress

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

HTMX = {"HX-Request": "true"}  # the header htmx adds to its requests


@pytest.fixture
def client():
    return TestClient(create_app(allowed_hosts={"testserver"}))


def output_lines(html: str) -> list[str]:
    """Pull the result lines out of the result block's <textarea>."""
    start = html.index('class="output"')
    body = html[html.index(">", start) + 1 : html.index("</textarea>", start)]
    return body.splitlines()


# --- main page -----------------------------------------------------------------------------------


def test_main_page_has_three_tabs(client):
    page = client.get("/").text
    for key in ("ip", "mac", "convert"):
        assert f'id="tab-{key}"' in page
        assert f'id="tool-{key}"' in page


@pytest.mark.parametrize("tab, checked", [("mac", "mac"), ("convert", "convert"), ("nonsense", "ip")])
def test_tab_query_selects_tab(client, tab, checked):
    page = client.get(f"/?tab={tab}").text
    assert f'id="tab-{checked}" class="tab-radio" checked' in page


def test_static_files_are_served(client):
    for name in ("style.css", "htmx.min.js", "app.js"):
        assert client.get(f"/static/{name}").status_code == 200


# --- IP generator --------------------------------------------------------------------------------


def test_ip_count_and_network(client):
    response = client.post("/ip", data={"count": "50", "network": "192.168.4.0/22"}, headers=HTMX)
    assert response.status_code == 200
    lines = output_lines(response.text)
    assert len(lines) == 50
    assert all(ipaddress.IPv4Address(line) in ipaddress.IPv4Network("192.168.4.0/22") for line in lines)
    assert "50 addresses from 192.168.4.0/22" in response.text


def test_htmx_gets_only_the_result_block(client):
    response = client.post("/ip", data={"count": "5"}, headers=HTMX)
    assert "<html" not in response.text
    assert "random private network" in response.text


def test_ip_mask_style(client):
    response = client.post(
        "/ip", data={"count": "3", "network": "192.168.4.0/24", "style": "mask"}, headers=HTMX
    )
    assert all(line.endswith(" 255.255.255.0") for line in output_lines(response.text))


def test_ip_count_with_thousands_separator(client):
    response = client.post("/ip", data={"count": "1,000"}, headers=HTMX)
    assert len(output_lines(response.text)) == 1000


def test_ip_host_bits_note(client):
    response = client.post("/ip", data={"network": "192.168.5.9/30"}, headers=HTMX)
    assert "rounded down from 192.168.5.9/30" in response.text


@pytest.mark.parametrize(
    "data, message",
    [
        ({"count": "abc"}, "isn&#39;t a whole number"),
        ({"network": "192.168.4.0/31"}, "/31 or /32"),
        ({}, "Give a count"),
        ({"count": "70000"}, "at most 65,534"),
    ],
)
def test_ip_errors_are_shown(client, data, message):
    response = client.post("/ip", data=data, headers=HTMX)
    assert response.status_code == 200
    assert 'class="flash bad"' in response.text
    assert message in response.text


def test_ip_without_javascript_returns_full_page(client):
    # No HX-Request header: a plain form post wants the whole page back, with
    # the IP tab selected, the form refilled and the result shown.
    response = client.post("/ip", data={"count": "7", "network": "192.168.9.0/24"})
    page = response.text
    assert "<html" in page
    assert 'id="tab-ip" class="tab-radio" checked' in page
    assert 'value="192.168.9.0/24"' in page
    assert "7 addresses from 192.168.9.0/24" in page


def test_user_input_is_escaped(client):
    response = client.post("/ip", data={"network": "<script>alert(1)</script>"}, headers=HTMX)
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


# --- MAC generator -------------------------------------------------------------------------------


def test_mac_default_is_local_lowercase_colon(client):
    response = client.post("/mac", data={"count": "10"}, headers=HTMX)
    lines = output_lines(response.text)
    assert len(lines) == 10
    for line in lines:
        assert line == line.lower() and line.count(":") == 5
        assert line[1] in "26ae"
    assert "locally administered" in response.text


def test_mac_oui_dotted_upper(client):
    data = {"count": "5", "mode": "oui", "oui": "00:1a:2b", "style": "dotted", "upper": "on"}
    response = client.post("/mac", data=data, headers=HTMX)
    assert all(line.startswith("001A.2B") for line in output_lines(response.text))
    assert "with prefix 00:1a:2b" in response.text


@pytest.mark.parametrize(
    "data, message",
    [
        ({"count": ""}, "Give a count"),
        ({"count": "5", "mode": "oui", "oui": "zz"}, "OUI prefix"),
        ({"count": "5", "mode": "oui", "oui": "01:00:5e"}, "multicast"),
        ({"count": "5", "style": "bare"}, "Unknown MAC format"),
    ],
)
def test_mac_errors_are_shown(client, data, message):
    response = client.post("/mac", data=data, headers=HTMX)
    assert 'class="flash bad"' in response.text
    assert message in response.text


# --- MAC converter -------------------------------------------------------------------------------


def test_convert_with_a_bad_line(client):
    pasted = "02:1a:2b:3c:4d:5e\nnot a mac\n021a.2b3c.4d5f\n"
    response = client.post("/convert", data={"macs": pasted, "style": "hyphen"}, headers=HTMX)
    assert output_lines(response.text) == ["02-1a-2b-3c-4d-5e", "02-1a-2b-3c-4d-5f"]
    assert "2 converted, 1 skipped" in response.text
    assert "Line 2 skipped, not a MAC: not a mac" in response.text


def test_convert_caps_the_warning_list(client):
    pasted = "\n".join(["junk"] * 30)
    response = client.post("/convert", data={"macs": pasted}, headers=HTMX)
    assert response.text.count("skipped, not a MAC") == 20
    assert "and 10 more skipped lines" in response.text


def test_convert_empty_paste_is_refused(client):
    response = client.post("/convert", data={"macs": "  \n "}, headers=HTMX)
    assert "Paste one or more" in response.text


def test_convert_too_many_lines_is_refused(client):
    pasted = "\n".join(["02:1a:2b:3c:4d:5e"] * 65_535)
    response = client.post("/convert", data={"macs": pasted}, headers=HTMX)
    assert "more than 65,534 lines" in response.text


# --- download ------------------------------------------------------------------------------------


def test_download_echoes_content_with_crlf(client):
    response = client.post("/download", data={"kind": "ip", "content": "192.168.4.1\n192.168.4.2\n\n"})
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="ip-addresses.txt"'
    assert response.content == b"192.168.4.1\r\n192.168.4.2\r\n"


def test_download_unknown_kind_is_refused(client):
    assert client.post("/download", data={"kind": "../etc", "content": "x"}).status_code == 400


def test_download_handles_a_full_slash_16(client):
    # 65,534 lines in "ip mask" style is about 2 MB: make sure the form post isn't cut short.
    lines = [f"172.16.{n // 256}.{n % 256} 255.255.0.0" for n in range(65_534)]
    response = client.post("/download", data={"kind": "ip", "content": "\n".join(lines)})
    assert response.content.count(b"\r\n") == 65_534


# --- local-only security checks ------------------------------------------------------------------


def test_wrong_host_is_refused():
    # Built with the real allowed hosts, so "testserver" (like evil.example) is refused.
    client = TestClient(create_app())
    assert client.get("/").status_code == 403


def test_post_from_another_site_is_refused(client):
    response = client.post("/ip", data={"count": "5"}, headers={"Origin": "http://evil.example"})
    assert response.status_code == 403


def test_post_from_own_page_is_allowed(client):
    response = client.post("/ip", data={"count": "5"}, headers={"Origin": "http://testserver", **HTMX})
    assert response.status_code == 200
