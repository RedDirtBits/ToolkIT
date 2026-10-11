"""
templating.py — the Jinja2 setup shared by every page.

Jinja2 templates are HTML with blanks in them ({{ summary }}) and simple
logic ({% for line in lines %}). Python fills in the blanks. Every value is
"auto-escaped": text like <script> typed into a form is shown as text, never
run as code in your browser.

render() adds the things EVERY page needs (app name, the list of tabs) so
each route only passes what's specific to it.
"""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import settings

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def wrap_after_commas(text: str) -> Markup:
    """HTML for a long comma-separated line that may wrap only BETWEEN items.

    Each item goes in a <span class="nowrap"> (never broken inside, so "57-59"
    stays whole), with <wbr> ("a line may break here") after each comma.
    Every item is escaped first, so the only HTML in the result is our own;
    Markup() then tells Jinja2 not to escape it again.
    Used by the VLAN list's compressed result (see _result.html).
    """
    items = [f'<span class="nowrap">{escape(item)}</span>' for item in text.split(",")]
    return Markup(",<wbr>".join(items))


# Make it usable in templates as {{ text | wrap_after_commas }}.
templates.env.filters["wrap_after_commas"] = wrap_after_commas

# The tabs on the main page: (key, label). The key is used in element ids
# (tab-ip, tool-ip), form posts (/ip) and the ?tab= address.
TABS = [
    ("ip", "IP generator"),
    ("subnet", "Subnet calculator"),
    ("iplist", "IP list cleanup"),
    ("vlan", "VLAN list"),
    ("mac", "MAC generator"),
    ("convert", "MAC converter"),
    ("hosts", "Hostname faker"),
    ("oui", "OUI lookup"),
]
TAB_KEYS = {key for key, _ in TABS}


def render(request: Request, template: str, status_code: int = 200, **context):
    """Render a full page or partial, with the common context added."""
    context.setdefault("app_name", settings.APP_NAME)
    context.setdefault("tabs", TABS)
    # The OUI tab's "list from <date>" panel is part of the full page.
    context.setdefault("oui_status", request.app.state.oui.status())
    return templates.TemplateResponse(request, template, context, status_code=status_code)
