"""limits.py — the one per-request size limit every tool shares.

Several tools refuse requests that are too big (the IP and MAC generators,
IP list cleanup, the hostname faker), and the web layer applies the same
limit to the MAC converter and the OUI lookup. Defining it once here means
changing it is one edit, and the copies can't drift apart.

It lives in tools/ rather than app/settings.py so the tools stay pure: they
never import anything from the web side of the app.
"""

# The most items (addresses, MACs or pasted lines) one request may hold: the
# usable hosts of a /16 (65,536 - 2). Big enough for any real job, small
# enough that a typo like 1000000 can't hang the page.
MAX_ITEMS = 65_534
