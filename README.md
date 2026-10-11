# ToolkIT

A small offline web app of everyday network utilities for network engineers: random IP and MAC address
generators, a subnet calculator, an IP list cleanup tool, a MAC address format converter, a hostname faker, and an offline MAC vendor (OUI)
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
- **Subnet calculator:** type `192.168.4.17/22`, `... 255.255.252.0` or an ACL wildcard
  `192.168.4.0 0.0.3.255` and get network, mask, wildcard, prefix, broadcast, usable range and count,
  and the address type (private, CGNAT, documentation...), each with its own Copy button. Optionally
  split the network into smaller subnets by prefix (`/26`) or count (`8`). /31 and /32 handled
  correctly (RFC 3021 point-to-point, single host).
- **IP list cleanup:** paste addresses and networks (one per line, prefix, mask or ACL wildcard) and get
  them deduplicated in their original order, sorted numerically (.2 before .10), and summarized into the
  fewest CIDR blocks that cover exactly the input (as prefixes, masks or ACL wildcards), plus the
  smallest single block that covers everything. Invalid lines are listed, never dropped silently.
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
| Subnet calculator | Everything about a subnet; split into smaller subnets | done |
| IP list cleanup | Deduplicate, sort and summarize addresses and networks | done |
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
- **Subnet calculator:** type an address with a prefix, mask or wildcard and press **Enter**. To
  split it, add a new prefix (`/26`) or a number of subnets (`8`) in **Split into**.
- **IP list cleanup:** paste addresses or networks one per line, choose how summarized blocks are
  written (prefix, mask or ACL wildcard) and click **Clean up**.
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
all of them. `?tab=subnet`, `?tab=iplist`, `?tab=mac`, `?tab=convert`, `?tab=hosts` or `?tab=oui` in the address opens another tab directly (handy as a bookmark).

### Why the IP list summary sometimes looks odd

The **Summarized for ACLs / prefix lists** box answers one specific question: *what is the smallest
set of address blocks that covers exactly these addresses, and not one address more?* That's what an
access list (ACL) or a prefix list needs. If it allowed a block that was too big, it would let in
devices it shouldn't.

Address blocks (CIDR blocks such as `/24` or `/29`) follow two rules. Their size is a power of two
(1, 2, 4, 8, 16... addresses), and each block must start at a multiple of its size. So a run of
addresses only becomes one block if it is exactly the right size and starts in exactly the right
place:

```
192.0.2.8 – .15   (8 addresses, starts at a multiple of 8)  →  192.0.2.8/29     one block
192.0.2.5 – .12   (8 addresses, starts at .5)               →  .5/32  .6/31  .8/30  .12/32
```

That's why a list of **individual devices** (for example, the in-use management addresses of one
subnet) comes out as many small blocks (`/32`, `/30`, `/29`...): the unused addresses between them
can't be included, so the gaps can't be bridged. The result is correct, it just isn't what people
expect. Lists that are already **range-shaped** (subnets plus a few hosts), as ACLs and prefix
lists usually are, merge into a short, tidy result.

To see the one network a set of addresses sits in, use **All fit in (one block)** instead. It
includes the unused addresses, and the **Extra addresses** count shows how many. The page shows a
short note when your list is mostly single addresses.

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
