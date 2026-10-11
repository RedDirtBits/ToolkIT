"""
__main__.py — start the ToolkIT web app. This is what runs when you type

    python -m app             (Linux)
    python\\python.exe -m app   (Windows, or just double-click run.bat)

It starts the web server on http://127.0.0.1:8780 and opens your browser
there. Press Ctrl+C (or close the window) to stop it.
"""

import argparse
import threading
import webbrowser

import uvicorn

from app import settings
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Start the {settings.APP_NAME} web app.")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = parser.parse_args()

    # Safety net: refuse to listen on anything but the laptop itself.
    if settings.HOST not in ("127.0.0.1", "localhost"):
        raise SystemExit(f"Refusing to start: HOST must be 127.0.0.1, not {settings.HOST!r} (see settings.py).")

    url = f"http://{settings.HOST}:{settings.PORT}/"
    print(f"{settings.APP_NAME} is starting at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        # Open the browser a moment later, once the server is listening.
        threading.Timer(1.5, webbrowser.open, args=[url]).start()

    # uvicorn is the web server that hands browser requests to FastAPI.
    uvicorn.run(create_app(), host=settings.HOST, port=settings.PORT, log_level="info")


if __name__ == "__main__":
    main()
