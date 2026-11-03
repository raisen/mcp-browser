"""Build the `--onedir` PyInstaller bundle.

Run through uv so PyInstaller never becomes a project dependency:

    uv run --with pyinstaller python packaging/build.py [--out DIR]

Work files and the generated spec go to a temp dir, never into the repo. Output:
`<out>/mcp-browser-<version>-<os>-<arch>.zip`; its SHA256 is printed.
The bundle is smoke-tested (`--help` runs, the web UI files are inside) before it is zipped.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "packaging" / "pyinstaller_entry.py"
NAME = "mcp-browser"

# Packages PyInstaller cannot see through static analysis (dynamic imports, data files).
COLLECT_SUBMODULES = ("uvicorn", "anyio", "mcp_browser", "mcp_browser_server")
COLLECT_DATA = ("mcp_browser_server", "jsonschema", "jsonschema_specifications", "mcp", "mcp_types")
COLLECT_ALL = ("pydantic_core", "mcp_browser_core", "httpx2")
HIDDEN_IMPORTS = ("filelock", "json5", "tomlkit")


def pyinstaller_args(dist: Path, work: Path) -> list[str]:
    args = [
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        NAME,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(work),
    ]
    for pkg in COLLECT_SUBMODULES:
        args += ["--collect-submodules", pkg]
    for pkg in COLLECT_DATA:
        args += ["--collect-data", pkg]
    for pkg in COLLECT_ALL:
        args += ["--collect-all", pkg]
    for mod in HIDDEN_IMPORTS:
        args += ["--hidden-import", mod]
    return [*args, str(ENTRY)]


def version() -> str:
    from mcp_browser_core import __version__

    return __version__


def archive_name() -> str:
    system = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    return f"{NAME}-{version()}-{system}-{machine}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def smoke_test(bundle: Path, exe: Path) -> None:
    subprocess.run([str(exe), "--help"], check=True, stdout=subprocess.DEVNULL)
    if not any(bundle.rglob("mcp_browser_server/static/index.html")):
        raise SystemExit("build failed: web UI files (static/index.html) are not in the bundle")


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcp-browser-build-") as tmp:
        dist, work = Path(tmp) / "dist", Path(tmp) / "work"
        subprocess.run([sys.executable, "-m", "PyInstaller", *pyinstaller_args(dist, work)], check=True)
        bundle = dist / NAME
        exe = bundle / (NAME + (".exe" if sys.platform == "win32" else ""))
        if not exe.is_file():
            raise SystemExit(f"build failed: {exe} missing")
        smoke_test(bundle, exe)
        archive = shutil.make_archive(str(out / archive_name()), "zip", root_dir=dist, base_dir=NAME)
    zip_path = Path(archive)
    print(f"sha256 {sha256(zip_path)}  {zip_path.name}")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="where the zip and checksums go")
    args = parser.parse_args()
    zip_path = build(args.out)
    print(f"built {zip_path}")


if __name__ == "__main__":
    main()
