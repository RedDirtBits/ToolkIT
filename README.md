# ToolkIT

A small offline web app of everyday network utilities for network engineers: random IP and MAC address
generators, a MAC address format converter, a hostname faker, and an offline MAC vendor (OUI)
lookup. Runs locally on Windows (portable, embedded Python) or
Linux.

## Why

Simple jobs like "give me 300 random IPs", "make me some fake MACs" or "convert this MAC to Cisco format"
usually mean opening several different websites. That's slow, and it doesn't work at sites with limited
internet access. ToolkIT puts these tools in one local page that works offline.

## Features

- **Random IP generator:** give a subnet (`/22` or `255.255.252.0`) and get random addresses filling it,
  or give a count (e.g. 300) and it picks the right subnet size (/23) for you. No duplicates, no network
  or broadcast addresses. Output as plain IPs, with prefix, or with mask.
- **Random MAC generator:** locally administered addresses by default (safe fakes that can't clash with a
  real vendor), fully random, or with a chosen OUI prefix.
- **MAC format converter:** paste one or many MACs and see them in every format at once
  (`aa:bb:cc:dd:ee:ff`, `aa-bb-cc-dd-ee-ff`, `aabb.ccdd.eeff`), each with its own Copy button.
- **Hostname faker:** paste a column of real hostnames and get a column of fakes, one per line in the
  same order, ready to paste back over the original. Parts you choose (e.g. a device role like `cor`)
  are kept, the rest become random letters/digits of the same shape, and the same real part always
  gets the same fake, so the data keeps its structure without its real names.
- **OUI lookup:** who made this MAC? Type a MAC (any format) or a prefix and get the vendor, from an
  offline copy of IEEE's official registry (all block sizes, longest prefix first). Paste many for a
  vendor column. **Reverse search:** type a vendor name and get all its prefixes, e.g. for a MAC
  filter. The list is downloaded from IEEE only when you click **Update** (or imported from a file).
- Copy to clipboard or download results.

## Project status

| Piece | What it does | Status |
|---|---|---|
| IP generator | Random IPs by subnet or count | done |
| MAC generator | Random MACs, locally administered by default | done |
| MAC converter | Convert between MAC formats | done |
| Web UI | One local page, a tab per tool | done |
| OUI lookup | MAC → vendor and vendor → prefixes, from an offline IEEE list | done |
| Hostname faker | Fake a list of hostnames, keeping chosen parts and the structure | done |

## Quick start (Windows, portable)

1. Download the **Windows embeddable package (64-bit)** for Python 3.14 from python.org and unzip it into
   a `python` folder inside this project.
2. Edit `python\python314._pth`: add a line `..` (so Python finds the app) and uncomment `import site`.
3. Install pip: download `get-pip.py` and run `python\python.exe get-pip.py`.
4. Install the packages: `python\python.exe -m pip install -r requirements.txt`.
5. Double-click **`run.bat`**. The app opens at `http://127.0.0.1:8780`.

## Development setup (Linux)

```bash
source ../venv/bin/activate          # the shared venv
pip install -r requirements-dev.txt
python -m app                        # start the app
python -m pytest                     # run the tests
```

## How to use it

Start the app (`run.bat` on Windows, `python -m app` on Linux); the browser opens at
`http://127.0.0.1:8780`. Pick a tab in the top bar:

- **IP generator:** type a count, a network, or both, pick the output style and click **Generate**.
- **MAC generator:** type a count, choose locally administered (safe fakes), fully random or a given OUI
  prefix, pick the format and click **Generate**.
- **MAC converter:** paste MACs one per line and click **Convert**: every format appears side by side,
  each with its own Copy button.
- **Hostname faker:** paste hostnames one per line (e.g. a spreadsheet column), list the parts to keep
  (`cor, dst, acc`), pick the case and click **Fake**. Paste the result back over the real column.
  Fake hostnames that belong together in one paste: each new paste gets new fakes.
- **OUI lookup:** the first time, click **Update from IEEE** (about 5 MB). Then type a MAC and press
  **Enter**; paste several (one per line) for a table and a "Vendors" column to copy. Under **Find a
  vendor's prefixes**, type part of a name. If Update can't get through a proxy, download the three
  files named on the page in your browser and **Import** each one.

Each result has **Copy** and **Download .txt** buttons. Tabs keep their results while you switch between
them; **Clear** resets one tab (fields back to defaults, result removed), and reloading the page clears
all of them. `?tab=mac`, `?tab=convert`, `?tab=hosts` or `?tab=oui` in the address opens another tab directly (handy as a bookmark).

## Folder layout

```
ToolkIT/
├── app/
│   ├── tools/    # the tools themselves (pure Python, no web code)
│   └── web/      # pages, forms, templates, CSS
├── tests/        # pytest tests
└── run.bat       # Windows launcher
```

## Running the tests

```bash
python -m pytest -q
```

## Security notes

- Listens on `127.0.0.1` only; checks `Host`, and `Origin`/`Referer` on form posts.
- Needs no credentials. The only data it stores is IEEE's public vendor list, in `data/oui/`
  (the hostname faker forgets everything after each paste).
- The only network access is the OUI **Update** button, which downloads IEEE's public files; nothing
  is ever sent off the machine.

## Built with

- Python, FastAPI, Jinja2, htmx
- Developed with the help of Claude (Anthropic) as a learning project.
