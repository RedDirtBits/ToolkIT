# Architecture — ToolkIT

How ToolkIT is built, and why. Written **as built** on 2026-10-12: the app was finished before this
document existed (see the first Decision), so it describes the code as it is, including where it
departs from the usual layer names.

## Purpose and context

ToolkIT is one local web page of everyday network utilities: random IP and MAC generators, a MAC
format converter, a subnet calculator, IP list cleanup and summarization, VLAN list expand/compress,
an offline OUI vendor lookup and a hostname faker. The full story is in [README.md](README.md).

- **What it does:** turns pasted or typed network values into other network values, offline.
- **Users and scale:** one engineer daily; colleagues optionally (most new to Python). No stored
  user data. A single request handles up to 65,534 lines (one full /16).
- **Where it runs:** a Windows laptop with the Windows *embeddable* Python 3.14 (no admin rights, no
  installer, behind a proxy), started by `run.bat`; also Linux for development.
- **Must work on:** Python 3.12–3.14, Linux and Windows.
- **Hosting and maintenance:** none. A portable folder (or release zip) on the user's own machine,
  no server, no running cost. Maintained by the author.

## Layers and folder layout

ToolkIT predates the standard `routers / services / repositories / core` folder names. The same
separation exists under different names:

| Standard layer | ToolkIT folder | Job |
|---|---|---|
| routers | `app/web/routes/` | Read the form, call a tool, describe the result (summary lines, tables). Some handlers are long (see Decisions). |
| (web helpers) | `app/web/*.py` | Shared web plumbing: security middleware, templates, response building, form parsing, the OUI list in memory |
| services | `app/tools/` | The tools: pure Python, no web imports, one file per tool, testable on their own |
| repositories | *(none as a folder)*: `app/tools/oui_data.py` (`load_folder`) and `app/tools/oui_update.py` | The only code touching the outside world: reads/writes IEEE's CSV files, downloads them |
| schemas | *(none)*: dataclasses inside each module (`ToolResult`, `Assignment`, ...) | Data shapes |
| core/config | `app/settings.py` | Plain constants: name, host, port, form limits, OUI folder |

```
ToolkIT/
├── app/
│   ├── __main__.py          # "python -m app": refuses any HOST but 127.0.0.1, starts uvicorn on :8780, opens the browser
│   ├── main.py              # create_app(): builds the FastAPI app (middleware, static files, routers); nothing else
│   ├── settings.py          # APP_NAME, HOST, PORT, MAX_CONVERT_LINES, MAX_FORM_FIELD_BYTES, OUI_DIR
│   ├── tools/               # the tools: pure Python, no web code
│   │   ├── ip_generator.py  # random IPv4 addresses by subnet and/or count; output styles
│   │   ├── subnet_calc.py   # subnet calculator: prefix/mask/wildcard in, every value out; splitting
│   │   ├── ip_list.py       # IP list cleanup: dedupe, numeric sort, exact summary, covering block
│   │   ├── vlan_list.py     # VLAN lists: parse numbers/ranges, compress, expand, free IDs
│   │   ├── mac_format.py    # read/write MAC formats (a MAC is held as a 48-bit int); the converter
│   │   ├── mac_generator.py # random MACs: locally administered (default), random, or a given OUI
│   │   ├── hostname_faker.py# fake a pasted list of hostnames, same shape, consistent per piece
│   │   ├── oui_data.py      # IEEE registries: parse CSV text, MAC -> vendor, vendor -> prefixes; load_folder() reads the files
│   │   └── oui_update.py    # the ONLY network code: download from IEEE or import a file; validate; atomic save
│   └── web/
│       ├── security.py      # Host check on every request, Origin/Referer check on every non-GET
│       ├── templating.py    # Jinja2 setup, render() (adds common context), TABS, wrap_after_commas filter
│       ├── responses.py     # ToolResult / OutputBlock / Table; tool_response(): htmx fragment or full page
│       ├── forms.py         # parse_count(), is_checked(), read_large_form() (8 MB fields)
│       ├── oui_state.py     # the OUI list in memory: loaded on first use, reloaded after Update/Import
│       ├── routes/          # one router per tab: pages, ip, subnet, iplist, vlan, mac, convert, hosts, oui; plus download
│       ├── templates/       # base.html, index.html (all tabs), _result.html, _oui_status.html, _mac_format_fields.html
│       └── static/          # style.css (UI kit + ToolkIT section), htmx.min.js (vendored), app.js (Copy, Clear, error messages)
├── tests/                   # pytest; fixtures/ieee/ holds small invented registry files
├── tools/build_release.py   # builds the colleague zip (allowlist, smoke test); not part of the app
├── run.bat, build_release.bat, GETTING-STARTED.html
├── ARCHITECTURE.md          # this file
└── README.md
```

## Rules

**Calls go one way:** `web/routes → tools`, and `web/routes → web/*` helpers. `tools/` never imports
FastAPI, Starlette or anything in `app/web/`. Inside `tools/`, a tool may use another's building
blocks (`mac_generator → mac_format`, `oui_data → mac_format`, `oui_update → oui_data`,
`ip_list → subnet_calc`), never the reverse of those.

**Enforced by:** code review and a grep (`grep -rn "fastapi\|starlette\|app\.web" app/tools/` finds
nothing). import-linter isn't adopted.

**Project-specific rules:**

- **Only `oui_update.py` uses the network**, and only when the user clicks Update. Nothing typed or
  pasted ever leaves the machine.
- **Only `oui_data.load_folder()` and `oui_update.py` touch the disk** (the `data/oui/` folder).
  Files are saved with an atomic replace (temporary file, then `os.replace`), and all three IEEE
  files are downloaded and validated before any is saved. The three saves are one after another,
  not all-or-nothing (see Error handling).
- **Random networks never come from 10.0.0.0/8**: only 172.16.0.0/12 and 192.168.0.0/16
  (`ip_generator.py`). A network the user types is used as given.
- **Every request is size-limited**: 65,534 addresses or lines (IP and MAC generators, converter,
  OUI lookup, hostname faker, IP list cleanup), 65,536 subnets in a split, 8 MB per form field
  (the VLAN list relies on this one), 50 MB per IEEE file. A typo like `1000000` gets a clear
  refusal instead of a hung page.
- **Generated lists never repeat a value.**
- **Tools take an optional `random.Random`**, so tests can seed it; normal use gets a fresh one.

## Data flow

**Example: the user asks for 300 random IPs.**

```
browser ──POST /ip (htmx)──▶ web/security.py         Host is 127.0.0.1? Origin is our page? else 403
                                  │
                                  ▼
                              web/routes/ip.py        reads count/network/style as text;
                                  │                   forms.parse_count("300") -> 300
                                  ▼
                              tools/ip_generator.py   parse_target(""), generate_ips(300): smallest
                                  │                   prefix that fits (/23), random block in
                                  │                   172.16/12 or 192.168/16, 300 unique hosts;
                                  │                   format_ips(..., "plain")
                                  ▼
                              web/routes/ip.py        builds a ToolResult (summary + one OutputBlock)
                                  │
                                  ▼
                              web/responses.py        HX-Request header? render _result.html only;
          ◀── HTML fragment ──┘                       no JavaScript? render the whole index.html
```

1. **Security middleware** checks the Host header (DNS-rebinding guard) and, for a POST, the
   Origin/Referer (CSRF guard).
2. **The router** reads the form fields as plain text and turns bad input into a friendly message
   (`FormError`), never a technical error page.
3. **The tool** does all the network logic, with no idea a web page exists. Its own errors
   (`IPGeneratorError`) carry messages safe to show.
4. **The router** wraps the result in a `ToolResult`; `tool_response()` sends just the result block
   to htmx, or the full page (tab selected, form refilled) to a plain form post.
5. **Copy** is done in the browser (`app.js`). **Download** posts the shown text back to
   `/download`, which returns it as a `.txt` file (re-running would give different random values).

The OUI tab adds one step: routes reach the in-memory list through `request.app.state.oui`
(`web/oui_state.py`), which reads the files once, on first use, and again after Update or Import.
Only the templates that show the "IEEE list" panel (`index.html`, `_oui_status.html`) ask it for its
status; result fragments for the other tabs never touch the OUI files.

## Data and storage

| Data | Stored where | Format | Sensitive? | In git? |
|---|---|---|---|---|
| IEEE OUI registries (MA-L, MA-M, MA-S) | `data/oui/` | IEEE's CSV files, as downloaded | No: public | No (git-ignored; each user downloads their own) |
| Everything typed or pasted | Memory, for one request | — | Possibly (work IPs, hostnames) | Never stored |

- **Credentials:** none.
- **Backups / recovery:** nothing to back up. If `data/oui/` is deleted, click Update again.

## External systems

| System | Accessed by | How | Failure behaviour |
|---|---|---|---|
| IEEE registry files (`standards-oui.ieee.org`) | `tools/oui_update.py` | HTTPS, `urllib` (uses the system proxy), own User-Agent (IEEE answers HTTP 418 to Python's default) | Timeout 60 s per file; any failure leaves the old files untouched and shows a message suggesting Import |

## Configuration

`app/settings.py` holds plain constants, not pydantic-settings. There's nothing a user needs to
override (see Decisions).

| Setting | Default | Why this value |
|---|---|---|
| `HOST` | `127.0.0.1` | localhost only; `__main__.py` refuses to start with anything else |
| `PORT` | `8780` | not 8000 (often taken) or ports used by other local apps |
| `MAX_CONVERT_LINES` | `65_534` | one /16's worth; stops a giant paste hanging the page |
| `MAX_FORM_FIELD_BYTES` | 8 MB | a full /16 in "ip mask" style is ~2 MB; Starlette's default is 1 MB |
| `OUI_DIR` | `<project>/data/oui` | beside the app, so the portable folder carries it |

Other limits live as constants in the module that uses them (`MAX_COUNT`, `MAX_LINES` in the tools,
`MAX_TABLE_ROWS` in two routes, `TIMEOUT` and `MAX_FILE_BYTES` in `oui_update.py`). Never in
settings: credentials or secrets (there are none).

## Security

- **Listens on** `127.0.0.1` only (`settings.py`, enforced again in `__main__.py`).
- **Host** checked on every request, **Origin/Referer** on every non-GET (`web/security.py`).
  A POST with neither header is allowed (a local tool like curl; a web page can't send one).
- **Output** auto-escaped by Jinja2. The one `Markup()` (`wrap_after_commas`) escapes each item first.
- **Credentials:** none.
- **Input limits:** see Rules. Download file names come from a fixed table, never from the form.

## Error handling

- Each tool raises its own error class (`IPGeneratorError`, `SubnetError`, `OUIUpdateError`, ...)
  whose message is written for the user. Routes catch them and show the message in the result area
  with HTTP 200 (htmx only swaps in 2xx responses).
- Lines that can't be read are listed (as warnings in the converter, IP list and VLAN list; as table
  rows marked "(not a MAC address)" in the OUI lookup), never dropped silently. At most 20 warnings
  are shown, plus a count of the rest.
- **Read, but maybe not as meant: a warning, not a guess.** The tool reports the fact, the route
  words it (decided 2026-10-12, review findings 5 and 6):
  - `0.0.0.0` / `255.255.255.255` as a mask or wildcard are always read as one host (/32), though
    each means "any" the other way round. `subnet_calc.read_as_single_host()` names the value; the
    subnet calculator warns per input, IP list cleanup once for all such lines (`read_as_host`).
  - The hostname faker only fakes ASCII letters and digits; anything else is copied through. Lines
    with non-ASCII characters are faked as usual and listed (`non_ascii`), so the user checks them
    before sharing. Only A-Z is lowercased (`_ASCII_LOWER`), so a fake keeps the original's length.
- Update/Import: the file is validated before saving; a failed download, a wrong file or a half
  write leaves the previous list in place. A save the disk refuses (read-only, full, locked by
  antivirus) becomes an `OUIUpdateError` naming the folder and reason. If an Update's second or
  third save fails, the earlier files are already new: the message says so, and Update again
  repairs it (decided 2026-10-12: rare, and a mixed list still works).
- **The OUI list fails soft** (`web/oui_state.py`): files that can't be read (locked, not text,
  not an IEEE list) or that vanished while the app runs become a status on the OUI tab ("couldn't
  be read: reason; Update or Import"), never an exception. The other tabs don't depend on the
  vendor list, so they must keep working when it's broken (review finding 1, 2026-10-12).
- **Unexpected errors** (a bug: HTTP 500, or the app not answering at all) are caught in the
  browser, not on the server: `app.js` listens for htmx's `htmx:responseError` and `htmx:sendError`
  and shows a plain-text message in the result area (or at the top of the OUI list panel, keeping
  its buttons). Without it, htmx ignores a failed request and the button just seems dead. One
  safety net in the browser covers "the app stopped" too, which a server-side handler couldn't
  (review finding 4, 2026-10-12).
- **Numbers are length-checked before `int()`**: Python refuses digit strings over 4,300 long with
  a plain `ValueError` the routes don't catch. Counts over 6 digits are refused as "far too large"
  (`web/forms.py`); VLAN items over 5 digits don't match the item pattern and are listed as skipped
  (review finding 3, 2026-10-12). The subnet and IP list patterns already capped their digits.

## Testing strategy

| Layer | How it's tested |
|---|---|
| tools | Unit tests, one file per tool; seeded `random.Random` for the generators; `tmp_path` for file writes |
| OUI download | A fake fetcher passed in (dependency injection); no test touches the network |
| web | FastAPI `TestClient` against `create_app(allowed_hosts={"testserver"}, oui_state=...)` with a fake OUI folder |
| release build | `tests/test_build_release.py` checks the allowlist settings; the build's own smoke test runs on Windows |
| browser (`app.js`) | No automated tests (no JavaScript test tools, on purpose). Checked by hand in a browser, or in headless Firefox with a scratch page that fires the events itself |

451 tests on Linux (Python 3.12, 2026-10-12); on Windows (3.14) the release-build tests are
skipped (404 when last run there, before the stage 4 fixes).
All test data is invented (documentation ranges, made-up hostnames and vendors).

**Coverage:** not measured yet (guardrail stage 2 not adopted).

## Guardrails in use

- [x] 1. ruff + mypy (`ruff check .`, `ruff format --check .`, `mypy`; settings in `pyproject.toml`)
- [ ] 2. pytest with coverage
- [ ] 3. pre-commit
- [ ] 4. secret scanning, bandit, pip-audit
- [ ] 5. import-linter
- [ ] 6. GitHub Actions CI

## Decisions

The day-to-day product decisions (formats, defaults, tab order) live in the project notes; the ones
below shape the design.

### 2026-10-11: Web UI, server-rendered, no build step

- **Context:** a tool used daily, on a locked-down laptop, possibly by colleagues new to Python.
- **Options considered:** command line; desktop GUI (tkinter isn't in the embeddable Python); local
  web page.
- **Chosen:** FastAPI + Jinja2 + htmx, one page with a CSS-only tab per tool.
- **Why:** a browser is already there; htmx swaps results in place without a JavaScript framework;
  plain form posts still work if JavaScript is off.
- **Consequences:** every route has to answer both htmx and plain posts (`tool_response()` does it once).

### 2026-10-11: Tools are pure Python, separate from the web code

- **Context:** each tool has fiddly rules (subnet edges, MAC bits, hostname shapes) that need many tests.
- **Chosen:** `app/tools/` holds all logic with no web imports; `app/web/routes/` only translates.
- **Why:** the rules can be tested in microseconds without a server, and could be reused by a CLI.
- **Consequences:** this is the standard `routers → services` split, under other folder names.

### 2026-10-11: OUI data is an offline file with an Update button

- **Context:** the point of the tool is working at sites with poor internet.
- **Options considered:** an online lookup API; a third-party download; IEEE's own CSVs.
- **Chosen:** IEEE's three official CSVs, downloaded on request into `data/oui/`, plus Import for
  networks where the download is blocked.
- **Why:** official, fixed URLs; works offline after one download; Import covers proxies.
- **Consequences:** the list goes stale until the user clicks Update; the page shows the file date.

### 2026-10-11: Hard request limits

- **Chosen:** at most 65,534 items per request (one /16), 8 MB per form field.
- **Why:** a typo must not hang the page; a /16 is the largest real need.

### 2026-10-12: Lifecycle adopted at stage 4; this document written as built

- **Context:** ToolkIT was designed and built (v1 and v2, published, release build prepared) before
  the project lifecycle existed. Gates 1–3 were never formally run; in particular, there was no
  design document and no independent design critique before code was written.
- **Options considered:** retro-fit gates 1–3 on paper; start at stage 4 and say so.
- **Chosen:** start at stage 4. This document records the design as it is.
- **Why:** pretending earlier gates passed would be dishonest. The stage 4 fresh review covers the
  whole repository, architecture included, so it also covers the missing design critique.
- **Consequences:** departures from the standard (below) are recorded rather than fixed up front;
  the fresh review decides whether any needs fixing.

### 2026-10-12: Known departures from the standard layout

- **Folder names:** `web/routes/` and `tools/` instead of `routers/` and `services/`;
  `settings.py` instead of `core/config.py`. Same separation, different names.
- **No `repositories/` folder:** the file and network code (`oui_data.load_folder()`,
  `oui_update.py`) sits inside `tools/`, next to pure logic. It's kept small and injectable (the
  fetcher is passed in), but a stranger wouldn't find "where the disk is touched" from folder names.
- **Plain constants, not pydantic-settings:** nothing is configurable by the user, so a settings
  class would add a moving part for no gain. Some limits live in the modules that use them rather
  than in `settings.py`.
- **No `schemas/`:** data shapes are dataclasses beside the code that uses them.
- **Long route handlers:** several (IP list, subnet, VLAN, OUI lookup) run to 40–60 lines, mostly
  building summary text and tables from a tool's result. That's presentation, but it also holds
  decisions (what to say when) that can only be tested through the web layer.
- **One limit, several copies:** 65,534 is defined separately in `settings.py` and in four tools;
  `MAX_TABLE_ROWS` in two routes.
- **Decided (2026-10-12, after the stage 4 review, `docs/reviews/2026-10-12-delivery.md`):**
  - Folder names, no `repositories/`, plain constants, no `schemas/`: **kept**. The separation is
    real (nothing in `tools/` imports web code); renaming would be churn with no behaviour gain,
    and a settings class or schema folder would be a moving part with no user.
  - Long route handlers: **kept** as presentation, except two rules that move into the tools (the
    IP generator's "host bits cleared" check and IP list's "mostly single addresses" test).
  - One limit, several copies: **to be fixed** in the review's fix pass: one `MAX_ITEMS` in
    `app/tools/limits.py` (so tools still don't import web settings), `MAX_TABLE_ROWS` once in
    `settings.py`.
  - Putting all OUI disk access in one file (e.g. `oui_files.py`): **later idea**, not done in the
    review's fix pass, so the fixes stay reviewable.

## Deliberately left out

- **No database:** nothing is stored except IEEE's public files.
- **No JavaScript framework or build step:** htmx (vendored) and ~100 lines of `app.js`.
- **No user accounts or logins:** one user, on their own machine, listening on localhost only.
- **No IPv6** in the calculators: not needed yet.
- **No reading of IPs/VLANs out of free text** (configs, `show` output): a different tool.
