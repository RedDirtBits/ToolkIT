"""
settings.py — one place for the app's name, address and tunable numbers.

Every other module imports values from here instead of hard-coding them, so
changing (for example) the port means editing one line.
"""

APP_NAME = "ToolkIT"

# Listen on the laptop itself only. NEVER change this to "0.0.0.0": that
# would let anyone on the network reach the app.
HOST = "127.0.0.1"
# 8780 rather than the common 8000 (or 8765, used by another app), so it doesn't clash
# with other local apps.
PORT = 8780

# The most lines the MAC converter accepts in one paste. Same limit as the
# generators (one /16's worth), so a giant paste can't hang the page.
MAX_CONVERT_LINES = 65_534

# Largest single form field accepted, in bytes. Starlette's default is 1 MB,
# but a full /16 of results in "ip mask" style is about 2 MB, and it comes
# back through the Download button (and big pastes into the converter).
MAX_FORM_FIELD_BYTES = 8 * 1024 * 1024
