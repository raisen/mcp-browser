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
import os
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


def find_signing_identity(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    if env := os.environ.get("CODESIGN_IDENTITY"):
        return env
    if sys.platform != "darwin":
        return None
    try:
        res = subprocess.run(
            ["security", "find-identity", "-v", "-p", "codesigning"],
            capture_output=True,
            text=True,
            check=True,
        )
        for kind in ("Developer ID Application:", "Apple Development:"):
            for line in res.stdout.splitlines():
                if kind in line:
                    start, end = line.find('"'), line.rfind('"')
                    if start != -1 and end > start:
                        return line[start + 1 : end]
    except Exception:
        pass
    return None


def fix_framework_symlinks(bundle: Path) -> None:
    fw = bundle / "_internal" / "Python.framework"
    if not fw.is_dir():
        return
    versions_dir = fw / "Versions"
    if not versions_dir.is_dir():
        return
    vers = [p.name for p in versions_dir.iterdir() if p.is_dir() and not p.is_symlink() and p.name != "Current"]
    if not vers:
        return
    current = versions_dir / "Current"
    if current.is_dir() and not current.is_symlink():
        current.rmdir()
    if not current.exists():
        current.symlink_to(vers[0])
    p_file = fw / "Python"
    if p_file.is_file() and not p_file.is_symlink():
        p_file.unlink()
        p_file.symlink_to("Versions/Current/Python")
    r_dir = fw / "Resources"
    if r_dir.is_dir() and not r_dir.is_symlink():
        shutil.rmtree(r_dir)
        r_dir.symlink_to("Versions/Current/Resources")


def sign_bundle(bundle: Path, exe: Path, identity: str) -> None:
    print(f"signing bundle with identity: {identity}")
    fix_framework_symlinks(bundle)
    fw = bundle / "_internal" / "Python.framework"
    if fw.is_dir():
        subprocess.run(["codesign", "--force", "--sign", identity, str(fw)], check=False)
    for p in bundle.rglob("*"):
        if p.is_file() and not p.is_symlink() and p.suffix in (".dylib", ".so"):
            subprocess.run(["codesign", "--force", "--sign", identity, str(p)], check=False)
    subprocess.run(
        ["codesign", "--force", "--options", "runtime", "--deep", "--sign", identity, str(exe)],
        check=True,
    )
    subprocess.run(["codesign", "-vvv", "--deep", "--strict", str(exe)], check=True)
    print("codesign verification passed")


def smoke_test(bundle: Path, exe: Path) -> None:
    subprocess.run([str(exe), "--help"], check=True, stdout=subprocess.DEVNULL)
    if not any(bundle.rglob("mcp_browser_server/static/index.html")):
        raise SystemExit("build failed: web UI files (static/index.html) are not in the bundle")


def create_archive(bundle: Path, out_path: Path) -> Path:
    zip_path = out_path.with_suffix(".zip")
    if shutil.which("zip"):
        subprocess.run(["zip", "-qry", str(zip_path), bundle.name], cwd=bundle.parent, check=True)
        return zip_path
    archive = shutil.make_archive(str(out_path), "zip", root_dir=bundle.parent, base_dir=bundle.name)
    return Path(archive)


def build(out: Path, identity: str | None = None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcp-browser-build-") as tmp:
        dist, work = Path(tmp) / "dist", Path(tmp) / "work"
        subprocess.run([sys.executable, "-m", "PyInstaller", *pyinstaller_args(dist, work)], check=True)
        bundle = dist / NAME
        exe = bundle / (NAME + (".exe" if sys.platform == "win32" else ""))
        if not exe.is_file():
            raise SystemExit(f"build failed: {exe} missing")
        sign_id = find_signing_identity(identity)
        if sign_id:
            sign_bundle(bundle, exe, sign_id)
        smoke_test(bundle, exe)
        zip_path = create_archive(bundle, out / archive_name())
    print(f"sha256 {sha256(zip_path)}  {zip_path.name}")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="where the zip and checksums go")
    parser.add_argument(
        "--identity",
        default=os.environ.get("CODESIGN_IDENTITY"),
        help="codesign identity (defaults to CODESIGN_IDENTITY env or auto-detect from keychain)",
    )
    args = parser.parse_args()
    zip_path = build(args.out, identity=args.identity)
    print(f"built {zip_path}")


if __name__ == "__main__":
    main()
