"""
main.py — build the FastAPI app and plug in every page.

create_app() is a "factory": a function that builds a fresh, fully wired
app. The launcher (app/__main__.py) calls it once; the tests call it with
their own allowed host name ("testserver").
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import settings
from app.web.routes import convert, download, hosts, ip, mac, pages
from app.web.security import DEFAULT_ALLOWED_HOSTS, local_only_middleware

STATIC_DIR = Path(__file__).parent / "web" / "static"


def create_app(allowed_hosts: set[str] | None = None) -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, description="Offline network utilities.")

    # Every request passes through the local-only check first.
    app.middleware("http")(local_only_middleware(allowed_hosts or DEFAULT_ALLOWED_HOSTS))

    # CSS, JavaScript (htmx, app.js), served from app/web/static/.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Each routes file is a "router": a bundle of related pages.
    for module in (pages, ip, mac, convert, hosts, download):
        app.include_router(module.router)

    return app
