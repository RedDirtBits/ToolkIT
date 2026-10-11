"""
Tests for tools/build_release.py (template: works unchanged for any app).

They read the script's own settings (APP_NAME, INCLUDE, REQUIRED,
EMPTY_FOLDERS) and build a FAKE project from them in a temporary folder: a
pretend app, a pretend embedded Python (python.exe is a tiny shell script, so
the smoke test can run on Linux), plus things that must NEVER ship (a CSV,
collected data, tests, scratch, .git, CLAUDE.md). Then they build a release and
look inside the zip.

Add app-specific tests below the generic ones if the app has its own rules.
"""

import os
import stat
import zipfile
from datetime import date

import pytest

from tools import build_release as br

TODAY = date(2026, 1, 2)
APP = br.APP_NAME

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake python.exe is a shell script (Linux/macOS)")


def write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def fake_python_exe(path, exit_code=0, output="smoke test ok"):
    """A 'python.exe' that's really a shell script: prints, then exits with exit_code."""
    write(path, f"#!/bin/sh\necho '{output}'\nexit {exit_code}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / APP
    # Everything the settings say a release needs.
    for entry in br.INCLUDE:
        target = root / entry
        if "." in entry:               # looks like a file
            write(target, "x\n")
        else:                          # a folder: give it one file
            write(target / "placeholder.txt", "x\n")
    for required in br.REQUIRED:
        if not (root / required).exists():
            write(root / required, "x\n")
    write(root / "app" / "__pycache__" / "main.cpython-314.pyc", "bytecode")
    fake_python_exe(root / "python" / "python.exe")
    write(root / "python" / "python314._pth", "python314.zip\n.\n..\nimport site\n")
    site = root / "python" / "Lib" / "site-packages"
    write(site / "somepkg" / "data" / "table.csv", "a,b\n")       # package data: allowed
    write(site / "_pytest" / "__init__.py")                         # dev package: left out
    write(site / "pytest-8.3.0.dist-info" / "RECORD", "_pytest/__init__.py,,\npytest-8.3.0.dist-info/RECORD,,\n")
    # Things that must NEVER ship.
    write(root / "data" / "output" / "x" / "metadata.json", "{}")
    write(root / "real_export.csv", "real,data\n")
    for folder in br.EMPTY_FOLDERS:
        write(root / folder / "my_real_input.csv", "real,data\n")
    write(root / "tests" / "test_app.py")
    write(root / "scratch" / "notes.txt")
    write(root / ".git" / "config")
    write(root / "CLAUDE.md")
    return root


def names_in(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        return set(archive.namelist())


def test_release_contains_the_allowlist_inside_one_folder(project):
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    for required in br.REQUIRED:
        assert f"{APP}/{required}" in names
    assert all(name.startswith(f"{APP}/") for name in names)


def test_private_and_development_files_stay_out(project):
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    outside_python = [n for n in names if not n.startswith(f"{APP}/python/")]
    for never in (".csv", "metadata.json", "/tests/", "scratch", ".git", "CLAUDE.md", "__pycache__", ".pyc"):
        assert not any(never in name for name in outside_python), never


def test_empty_folders_hold_only_their_note(project):
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    for folder in br.EMPTY_FOLDERS:
        assert [n for n in names if n.startswith(f"{APP}/{folder}/")] == [f"{APP}/{folder}/README.txt"]


def test_dev_packages_left_out_package_data_kept(project):
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    assert not any("_pytest" in n for n in names)
    assert f"{APP}/python/Lib/site-packages/somepkg/data/table.csv" in names


def test_a_csv_inside_an_included_folder_stops_the_build(project):
    folder = next(e for e in br.INCLUDE if "." not in e and e != "python")
    write(project / folder / "leftover.csv", "real,data\n")
    with pytest.raises(br.ReleaseError, match="leftover.csv"):
        br.build(project, run_smoke_test=False, today=TODAY)


def test_missing_python_or_pth_line_stops_the_build(project):
    write(project / "python" / "python314._pth", "python314.zip\n.\nimport site\n")
    if br.PTH_NEEDS_PARENT:
        with pytest.raises(br.ReleaseError, match="no '..' line"):
            br.build(project, run_smoke_test=False, today=TODAY)
    else:
        # The launcher finds the app without the ".." line, so the build goes ahead.
        br.build(project, run_smoke_test=False, today=TODAY)
    (project / "python" / "python.exe").unlink()
    with pytest.raises(br.ReleaseError, match="python/python.exe"):
        br.build(project, run_smoke_test=False, today=TODAY)


def test_smoke_test_pass_and_fail(project, capsys):
    br.build(project, run_smoke_test=True, today=TODAY)
    assert "smoke test ok" in capsys.readouterr().out
    fake_python_exe(project / "python" / "python.exe", exit_code=1, output="ImportError")
    with pytest.raises(br.ReleaseError, match="smoke test failed"):
        br.build(project, run_smoke_test=True, today=TODAY)


def test_zip_names_never_overwrite(project):
    first = br.build(project, run_smoke_test=False, today=TODAY)
    second = br.build(project, run_smoke_test=False, today=TODAY)
    assert (first.name, second.name) == (f"{APP}-2026-01-02.zip", f"{APP}-2026-01-02-2.zip")


# --- ToolkIT's own rules ---------------------------------------------------------------------------


def test_toolkit_release_is_just_the_app_python_launcher_and_guide(project):
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    top_level = {name.split("/")[1] for name in names}
    assert top_level == {"app", "python", "run.bat", "GETTING-STARTED.html"}


def test_vendor_list_never_ships_even_when_downloaded(project):
    # The build machine has a downloaded IEEE list; colleagues fetch their own with Update.
    write(project / "data" / "oui" / "oui.csv", "Registry,Assignment,Organization Name,Organization Address\n")
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    assert not any("/data/" in name or name.endswith(".csv") for name in names if "/python/" not in name)


def test_test_packages_dropped_app_packages_and_colorama_kept(project):
    site = project / "python" / "Lib" / "site-packages"
    for package, folder in [("httpx2", "httpx2"), ("truststore", "truststore"), ("colorama", "colorama"), ("anyio", "anyio")]:
        write(site / folder / "__init__.py")
        write(site / f"{package}-1.0.dist-info" / "RECORD", f"{folder}/__init__.py,,\n{package}-1.0.dist-info/RECORD,,\n")
    names = names_in(br.build(project, run_smoke_test=False, today=TODAY))
    inside = f"{APP}/python/Lib/site-packages/"
    assert f"{inside}colorama/__init__.py" in names and f"{inside}anyio/__init__.py" in names
    assert not any(n.startswith((f"{inside}httpx2", f"{inside}truststore")) for n in names)


def test_smoke_test_builds_the_real_app():
    # The smoke test must exercise create_app(), not just import the package.
    assert "create_app()" in " ".join(br.SMOKE_TEST)
