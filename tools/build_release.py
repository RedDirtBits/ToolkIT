"""
build_release.py — bundle the app into a zip that's safe to share with colleagues.

    python\\python.exe tools\\build_release.py        (Windows; or double-click build_release.bat)
    python tools/build_release.py                    (Linux: builds, but can't run the smoke test)

What it makes:  build/<APP_NAME>-<date>.zip, containing one <APP_NAME>/ folder with
only what a colleague needs to unzip and run: the app, the embedded Python with
its packages, the launcher and a getting-started page. Never the git history,
tests, scratch files, developer docs, collected data or inventory files.

How it stays safe:
  1. ALLOWLIST: only the paths listed in INCLUDE go in. Anything new that appears
     in the project later stays out unless someone deliberately adds it here.
     (A blocklist would do the opposite: let new things in until someone
     remembers to block them. That's how a data folder ends up in a zip.)
  2. CHECKS before writing: no forbidden files (CSV, collected data, secrets),
     and the parts needed to start are present.
  3. SMOKE TEST (Windows only): the bundled Python is started from the staged
     copy and must import the app, so a broken bundle is caught here, not on a
     colleague's laptop.

The settings block below is the only part specific to an app. To use it in a
project: copy this file to <project>/tools/, copy build_release.bat to the
project root, copy tests/test_build_release.py to <project>/tests/, then edit
the settings block (and the .bat's app name).
Standard library only, so it runs on the embedded Python with nothing installed.
"""

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath

# =============================================================================
# SETTINGS FOR THIS APP: the only part to edit when reusing this script
# (Filled in for ToolkIT from the shared release-build template.)
# =============================================================================

APP_NAME = "ToolkIT"  # folder name inside the zip, and the zip's name

# Files and folders (relative to the project root) that go into the release.
# Folders are included with everything inside them, minus SKIP_NAMES below.
# Only list what a colleague needs to RUN the app.
INCLUDE = [
    "app",  # the application package
    "python",  # the embedded Python, with the app's packages installed
    "run.bat",  # the launcher
    "GETTING-STARTED.html",  # the colleague guide
    # Nothing else: ToolkIT has no config or input files. data/ (the IEEE vendor
    # list) stays out on purpose: each colleague downloads it with the OUI tab's
    # Update button, and the app creates data/oui/ itself when they do.
]

# Empty folders the app expects, each with a short note file explaining it.
# {folder: note text}. Created fresh: the real folders' contents (your own
# data or input files) are never copied. Example:
#   EMPTY_FOLDERS = {"inventory": "Put your inventory CSV here, named switches.csv.\n"}
# ToolkIT needs none (it creates data/oui/ itself on the first Update).
EMPTY_FOLDERS: dict[str, str] = {}

# Must exist in the release, or it won't start on a colleague's machine.
REQUIRED = ["run.bat", "python/python.exe", "app/__main__.py", "GETTING-STARTED.html"]

# Python packages installed only for development (tests). Their files are left
# out of the bundled Python. Names as pip knows them (the .dist-info folder).
# Don't guess: list what `pip install --dry-run --report - pytest httpx2` would
# install, minus anything the app itself also needs (for a FastAPI app keep
# anyio, h11, idna, typing_extensions, and colorama, which uvicorn's click needs
# on Windows). See playbooks/RELEASE-BUILD.md.
# Checked for ToolkIT (2026-10-11) against the bundled python/: none of these is
# needed by fastapi, uvicorn, jinja2, python-multipart or pydantic. colorama is
# kept (tiny; uvicorn's console colours on Windows).
DEV_PACKAGES = [
    "pytest",
    "pluggy",
    "iniconfig",
    "packaging",
    "pygments",  # pytest
    "httpx2",
    "httpcore2",
    "truststore",  # httpx2 (FastAPI's test client)
]

# Does the embedded Python's ._pth file need a ".." line to find the app?
# ToolkIT: yes, run.bat starts it with "python\python.exe -m app".
#   True:  launched as "python -m app" or "python app\..." (the embeddable Python
#          ignores the current folder unless the ._pth file lists it).
#   False: launched as "python -m uvicorn app.main:app" from the app folder;
#          uvicorn puts that folder on sys.path itself (--app-dir, default ".").
PTH_NEEDS_PARENT = True

# The command the smoke test runs with the bundled Python, from the release
# folder. It must exit with code 0. Make it exercise real startup without
# opening a server or a window. EDIT for the app, e.g. for a FastAPI app with
# a create_app() factory:
#   ["-c", "from app.main import create_app; create_app(); print('smoke test ok')"]
# or, for an app launched by uvicorn without a ".." line (PTH_NEEDS_PARENT = False),
# import it the way uvicorn does:
#   ["-c", "import sys; sys.path.insert(0, '.'); import app.main; print('smoke test ok')"]
# ToolkIT: build the whole app (every route, template folder and static folder),
# and check the subnet calculator answers, without starting the server.
SMOKE_TEST = [
    "-c",
    "from app.main import create_app; create_app(); "
    "from app.tools.subnet_calc import calculate; assert str(calculate('192.0.2.9/30').network) == '192.0.2.8/30'; "
    "print('smoke test ok')",
]

# =============================================================================
# Generic part: no app-specific knowledge below this line
# =============================================================================

# Never copied, anywhere: caches and editor/OS clutter.
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store", "Thumbs.db"}
SKIP_SUFFIXES = {".pyc", ".pyo"}

# A release must never contain these OUTSIDE the bundled Python (packages in
# python/ legitimately contain folders named "data" or "tests"). Patterns are
# matched against each part of the path inside the release.
FORBIDDEN_PATTERNS = [
    "*.csv",  # inventories and exports
    "metadata.json",  # collected output's records
    ".env",
    "*.key",
    "*.pem",
    "id_rsa*",
    "id_ed25519*",  # secrets
    ".git",
    "tests",
    "scratch",
    "data",
    "docs",
    "CLAUDE.md",
    "LEARNING.md",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ReleaseError(Exception):
    """The release can't be built safely; the message says why."""


def dev_package_files(python_dir: Path, packages: list[str]) -> set[Path]:
    """Every file belonging to the given installed packages, so they can be skipped.

    pip records each installed package's files in <name>-<version>.dist-info/RECORD
    (one path per line, relative to site-packages). Reading that list is exact:
    no guessing which folders belong to which package.
    """
    skip: set[Path] = set()
    site_packages = python_dir / "Lib" / "site-packages"
    if not site_packages.is_dir():
        return skip
    wanted = {name.lower().replace("-", "_") for name in packages}
    for info in site_packages.glob("*.dist-info"):
        name = info.name.split("-")[0].lower().replace("-", "_")
        if name not in wanted:
            continue
        record = info / "RECORD"
        if record.is_file():
            for line in record.read_text(encoding="utf-8").splitlines():
                relative = line.split(",")[0]
                if relative:
                    skip.add((site_packages / relative).resolve())
        skip.add(info.resolve())  # the .dist-info folder itself
    return skip


def collect_files(root: Path) -> list[tuple[Path, PurePosixPath]]:
    """(file on disk, path inside the release) for everything in INCLUDE."""
    skip_dev = dev_package_files(root / "python", DEV_PACKAGES)
    files: list[tuple[Path, PurePosixPath]] = []

    def wanted(path: Path) -> bool:
        if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
            return False
        resolved = path.resolve()
        return resolved not in skip_dev and not any(parent in skip_dev for parent in resolved.parents)

    for entry in INCLUDE:
        source = root / entry
        if not source.exists():
            continue  # Reported by check_release() if it's REQUIRED.
        if source.is_file():
            files.append((source, PurePosixPath(entry)))
            continue
        # os.walk lets us prune skipped folders instead of walking into them.
        for folder, dirnames, filenames in os.walk(source, followlinks=False):
            folder_path = Path(folder)
            dirnames[:] = sorted(d for d in dirnames if wanted(folder_path / d))
            for filename in sorted(filenames):
                path = folder_path / filename
                if wanted(path) and not path.is_symlink():
                    files.append((path, PurePosixPath(path.relative_to(root).as_posix())))
    return files


def check_release(root: Path, files: list[tuple[Path, PurePosixPath]]) -> list[str]:
    """Problems that make the release unsafe or broken. Empty list = good to go."""
    problems = []
    names = {str(inside) for _, inside in files}

    for inside in sorted(names):
        parts = PurePosixPath(inside).parts
        if parts[0] == "python":
            continue  # Inside the bundled Python, package contents are fine.
        for part in parts:
            if any(fnmatch.fnmatch(part, pattern) for pattern in FORBIDDEN_PATTERNS):
                problems.append(f"forbidden file would be included: {inside} (matches '{part}')")
                break

    for required in REQUIRED:
        if required not in names:
            problems.append(f"required file is missing: {required}")

    # The embedded Python only finds the app if its ._pth file has a ".." line
    # (the app's code sits beside the python folder, not inside it), unless the
    # launcher puts the app folder on sys.path another way (PTH_NEEDS_PARENT).
    pth_files = sorted((root / "python").glob("python3*._pth"))
    if not pth_files:
        problems.append("no python/python3XX._pth file found (is the embedded Python set up?)")
    elif PTH_NEEDS_PARENT and not any(
        line.strip() == ".." for line in pth_files[0].read_text(encoding="utf-8").splitlines()
    ):
        problems.append(f"{pth_files[0].name} has no '..' line, so the bundled Python won't find the app")
    return problems


def stage(files: list[tuple[Path, PurePosixPath]], release_dir: Path) -> None:
    """Copy the files into a fresh folder laid out exactly as the release."""
    if release_dir.exists():
        shutil.rmtree(release_dir)
    for source, inside in files:
        target = release_dir / inside
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for folder, note in EMPTY_FOLDERS.items():
        (release_dir / folder).mkdir(parents=True, exist_ok=True)
        (release_dir / folder / "README.txt").write_text(note, encoding="utf-8", newline="\r\n")


def smoke_test(release_dir: Path) -> str:
    """Run the bundled Python from the staged release; return its output or raise."""
    python = release_dir / "python" / "python.exe"
    result = subprocess.run(
        [str(python), *SMOKE_TEST], cwd=release_dir, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise ReleaseError(f"smoke test failed (exit {result.returncode}):\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def write_zip(release_dir: Path, zip_path: Path) -> None:
    """Zip the staged folder. Paths inside start with <APP_NAME>/ so unzipping makes one folder."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(release_dir.rglob("*")):
            if path.is_file():
                archive.write(path, PurePosixPath(APP_NAME) / path.relative_to(release_dir).as_posix())


def next_zip_path(build_dir: Path, today: date) -> Path:
    """build/<APP_NAME>-<date>.zip, or -2, -3, ... if that day's name is taken."""
    base = f"{APP_NAME}-{today.isoformat()}"
    candidate, n = build_dir / f"{base}.zip", 2
    while candidate.exists():
        candidate, n = build_dir / f"{base}-{n}.zip", n + 1
    return candidate


def build(root: Path = PROJECT_ROOT, run_smoke_test: bool | None = None, today: date | None = None) -> Path:
    """Build the release zip and return its path. Raises ReleaseError if it isn't safe."""
    files = collect_files(root)
    problems = check_release(root, files)
    if problems:
        raise ReleaseError("Release NOT built:\n  - " + "\n  - ".join(problems))

    build_dir = root / "build"
    release_dir = build_dir / APP_NAME
    build_dir.mkdir(exist_ok=True)
    stage(files, release_dir)

    # python.exe only runs on Windows; elsewhere the smoke test is skipped.
    if run_smoke_test is None:
        run_smoke_test = os.name == "nt"
    if run_smoke_test:
        print(f"Smoke test: {smoke_test(release_dir)}")
        # The smoke test may have created runtime folders (e.g. data/); a
        # release starts clean, so stage again from scratch.
        stage(files, release_dir)
    else:
        print("Smoke test skipped (only possible on Windows, where python.exe runs).")

    zip_path = next_zip_path(build_dir, today or date.today())
    write_zip(release_dir, zip_path)
    return zip_path


def summary(files: list[tuple[Path, PurePosixPath]]) -> str:
    """Top-level entries with file counts and sizes, for a quick visual check."""
    totals: dict[str, list[int]] = {}
    for source, inside in files:
        top = inside.parts[0]
        count_size = totals.setdefault(top, [0, 0])
        count_size[0] += 1
        count_size[1] += source.stat().st_size
    lines = [
        f"  {top:<24} {count:>6} files  {size / 1_048_576:8.1f} MB"
        for top, (count, size) in sorted(totals.items())
    ]
    lines += [f"  {folder + '/':<24} {'(empty, with README.txt)':>28}" for folder in EMPTY_FOLDERS]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Build a shareable {APP_NAME} release zip.")
    parser.add_argument("--list", action="store_true", help="only show what would be included, then stop")
    args = parser.parse_args()

    files = collect_files(PROJECT_ROOT)
    print(f"{APP_NAME} release contents:\n{summary(files)}\n")
    if args.list:
        for _, inside in files:
            if inside.parts[0] != "python":
                print(f"  {inside}")
        print("  (python/ contents not listed)")
        return 0
    try:
        zip_path = build()
    except ReleaseError as exc:
        print(exc)
        return 1
    print(f"\nRelease built: {zip_path}  ({zip_path.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
