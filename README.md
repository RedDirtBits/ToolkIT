# ToolkIT

A small offline web app of everyday network utilities for network engineers: random IP and MAC address
generators and a MAC address format converter. Runs locally on Windows (portable, embedded Python) or
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
- **MAC format converter:** paste one or many MACs and convert between `aa:bb:cc:dd:ee:ff`,
  `aa-bb-cc-dd-ee-ff` and `aabb.ccdd.eeff`, upper or lower case.
- Copy to clipboard or download results.

## Project status

| Piece | What it does | Status |
|---|---|---|
| IP generator | Random IPs by subnet or count | done |
| MAC generator | Random MACs, locally administered by default | done |
| MAC converter | Convert between MAC formats | done |
| Web UI | One local page, a tab per tool | done |
| OUI lookup | Vendor lookup from an offline IEEE list | later (v2) |
| Hostname generator | Random hostnames from a pattern | later (v2) |

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
- **MAC converter:** paste MACs one per line, pick the format and click **Convert**.

Each result has **Copy** and **Download .txt** buttons. Tabs keep their results while you switch between
them. `?tab=mac` or `?tab=convert` in the address opens another tab directly (handy as a bookmark).

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
- Needs no credentials and stores no data. Nothing leaves the machine.

## Built with

- Python, FastAPI, Jinja2, htmx
- Developed with the help of Claude (Anthropic) as a learning project.
