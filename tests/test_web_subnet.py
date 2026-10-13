"""Tests for the subnet calculator tab (the engine itself is tested in test_subnet_calc.py)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.web.oui_state import OUIState

HTMX = {"HX-Request": "true"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(allowed_hosts={"testserver"}, oui_state=OUIState(tmp_path)))


def details(html: str) -> dict[str, str]:
    """The label -> value rows of the result, as shown on the page."""
    pairs = re.findall(
        r'<th scope="row">(.*?)</th>\s*<td><span id="[^"]+" class="detail-value">(.*?)</span>', html
    )
    return dict(pairs)


def test_calculate_shows_every_value_with_copy(client):
    response = client.post("/subnet", data={"address": "192.168.4.17 255.255.252.0"}, headers=HTMX)
    values = details(response.text)
    assert values == {
        "Network": "192.168.4.0/22",
        "Subnet mask": "255.255.252.0",
        "Wildcard mask": "0.0.3.255",
        "Prefix length": "/22",
        "Broadcast": "192.168.7.255",
        "First usable": "192.168.4.1",
        "Last usable": "192.168.7.254",
        "Usable hosts": "1,022",
        "Total addresses": "1,024",
        "Address type": "Private (RFC 1918)",
    }
    assert "192.168.4.17 is in 192.168.4.0/22" in response.text
    # One Copy button per value, each pointing at its own value.
    assert response.text.count('data-copy="subnet-detail-') == 10


def test_slash_31_explains_no_broadcast(client):
    response = client.post("/subnet", data={"address": "198.51.100.6/31"}, headers=HTMX)
    assert "point-to-point" in details(response.text)["Broadcast"]


def test_split_by_prefix(client):
    data = {"address": "192.168.4.0/24", "split": "/26"}
    response = client.post("/subnet", data=data, headers=HTMX)
    assert "split into 4 × /26" in response.text
    assert (
        "<td>192.168.4.64/26</td><td>192.168.4.65 – 192.168.4.126</td><td>192.168.4.127</td>" in response.text
    )
    box = response.text[response.text.index('id="subnets-output"') :]
    body = box[box.index(">") + 1 : box.index("</textarea>")].removeprefix("\n")
    assert body.split("\n") == [f"192.168.4.{n}/26" for n in (0, 64, 128, 192)]


def test_split_by_count(client):
    response = client.post("/subnet", data={"address": "203.0.113.0/24", "split": "3"}, headers=HTMX)
    assert "split into 4 × /26" in response.text


def test_split_into_slash_32_shows_single_hosts(client):
    response = client.post("/subnet", data={"address": "192.0.2.0/30", "split": "/32"}, headers=HTMX)
    assert "<td>192.0.2.1/32</td><td>192.0.2.1</td><td>none</td>" in response.text


@pytest.mark.parametrize(
    "data, message",
    [
        ({"address": ""}, "Type an address"),
        ({"address": "192.168.4.17"}, "has no prefix or mask"),
        ({"address": "192.168.4.0/24", "split": "/20"}, "must be longer"),
        ({"address": "192.168.4.0/24", "split": "abc"}, "isn&#39;t a split size"),
    ],
)
def test_errors_are_shown(client, data, message):
    response = client.post("/subnet", data=data, headers=HTMX)
    assert message in response.text


def test_without_javascript_returns_the_subnet_tab(client):
    response = client.post("/subnet", data={"address": "192.168.4.17/22", "split": "/24"})
    assert 'id="tab-subnet" class="tab-radio" checked' in response.text
    assert 'value="192.168.4.17/22"' in response.text and 'value="/24"' in response.text


def test_input_is_escaped(client):
    response = client.post("/subnet", data={"address": "<b>x</b>/24"}, headers=HTMX)
    assert "<b>" not in response.text


def test_subnets_download_name(client):
    response = client.post("/download", data={"kind": "subnets", "content": "192.0.2.0/25\n192.0.2.128/25"})
    assert 'filename="subnets.txt"' in response.headers["content-disposition"]


def test_copy_works_for_values_that_are_not_text_boxes(client):
    script = client.get("/static/app.js").text
    assert '"value" in source ? source.value : source.textContent' in script


@pytest.mark.parametrize(
    ("address", "other"), [("192.0.2.5 0.0.0.0", "mask"), ("0.0.0.0 255.255.255.255", "wildcard")]
)
def test_ambiguous_size_is_warned(client, address, other):
    response = client.post("/subnet", data={"address": address}, headers=HTMX)
    assert "as a single host (/32)" in response.text
    assert f"As a {other} it would mean" in response.text
    assert "0.0.0.0/0" in response.text


def test_clear_size_has_no_warning(client):
    response = client.post("/subnet", data={"address": "192.0.2.5/32"}, headers=HTMX)
    assert "as a single host" not in response.text
