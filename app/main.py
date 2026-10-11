"""
main.py — build the FastAPI app and plug in every page.

create_app() is a "factory": a function that builds a fresh, fully wired
app. The launcher (app/__main__.py) calls it once; the tests call it with
their own allowed host name ("testserver") and OUI folder.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import settings
from app.web.oui_state import OUIState
from app.web.routes import convert, download, hosts, ip, iplist, mac, oui, pages, subnet
from app.web.security import DEFAULT_ALLOWED_HOSTS, local_only_middleware

STATIC_DIR = Path(__file__).parent / "web" / "static"


def create_app(allowed_hosts: set[str] | None = None, oui_state: OUIState | None = None) -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, description="Offline network utilities.")

    # The OUI vendor list, loaded on first use and kept in memory (see oui_state.py).
    # Tests pass their own, pointing at fake files.
    app.state.oui = oui_state or OUIState(settings.OUI_DIR)

    # Every request passes through the local-only check first.
    app.middleware("http")(local_only_middleware(allowed_hosts or DEFAULT_ALLOWED_HOSTS))

    # CSS, JavaScript (htmx, app.js), served from app/web/static/.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Each routes file is a "router": a bundle of related pages.
    for module in (pages, ip, subnet, iplist, mac, convert, hosts, oui, download):
        app.include_router(module.router)

    return app
