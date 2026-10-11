"""
security.py — make sure only YOUR browser, on this laptop, can use the app.

Listening on 127.0.0.1 already keeps other computers out. But there are two
sneakier ways a malicious web page open in your browser could reach a local
app, and this guards against both:

  1. Cross-site request forgery (CSRF): a page on evil.example contains a
     hidden form that POSTs to http://127.0.0.1:8780/... Your browser
     would happily send it. ToolkIT holds nothing secret, but the check is
     cheap and keeps every app the same. Defense: browsers attach an "Origin"
     header saying which site a POST came from; anything that changes
     something (POST) must come from this app's own pages.

  2. DNS rebinding: evil.example tricks the browser into thinking its own
     name points at 127.0.0.1, then reads the app's pages as if they were
     its own. Defense: the browser still sends "Host: evil.example", so
     only requests addressed to 127.0.0.1 / localhost are answered.
"""

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import PlainTextResponse

DEFAULT_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

# Methods that only read. Everything else must pass the Origin check.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def local_only_middleware(allowed_hosts: set[str]):
    """Build the middleware function. (A "middleware" sees every request before any page does.)"""

    async def middleware(request: Request, call_next):
        # 1. The Host header must name this laptop.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in allowed_hosts:
            return PlainTextResponse("Forbidden: this app only answers requests addressed to 127.0.0.1.", 403)

        # 2. Anything that changes something must come from our own pages.
        if request.method not in SAFE_METHODS:
            source = request.headers.get("origin") or request.headers.get("referer")
            # No Origin/Referer at all means a non-browser tool (e.g. curl
            # on this laptop), which a web page can't impersonate.
            if source and urlsplit(source).hostname not in allowed_hosts:
                return PlainTextResponse("Forbidden: request did not come from this app's pages.", 403)

        return await call_next(request)

    return middleware
