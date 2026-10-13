"""
pages.py — the main page: one tab per tool (the list is TABS in templating.py).

GET /           opens on the IP generator tab
GET /?tab=mac   opens on another tab (handy as a bookmark)
"""

from fastapi import APIRouter, Request

from app.web.templating import TAB_KEYS, render

router = APIRouter()


@router.get("/")
def index(request: Request, tab: str = "ip"):
    # An unknown ?tab= value quietly falls back to the first tab.
    return render(request, "index.html", tab=tab if tab in TAB_KEYS else "ip")
