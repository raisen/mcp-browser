"""Build macOS App bundle and .dmg disk image with embedded CLI."""

from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MACOS_DIR = ROOT / "packaging" / "macos"
LOGO_PATH = ROOT / "site" / "images" / "logo.png"

ICON_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def current_arch() -> str:
    return platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")


def generate_app_icon(out_icns: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mcp-browser-icon-") as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        base_png = Path(tmp) / "base.png"

        subprocess.run(
            ["sips", "--cropToHeightWidth", "1536", "1536", str(LOGO_PATH), "--out", str(base_png)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        for name, size in ICON_SIZES:
            target = iconset / name
            subprocess.run(
                ["sips", "-z", str(size), str(size), str(base_png), "--out", str(target)],
                check=True,
                stdout=subprocess.DEVNULL,
            )

        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out_icns)], check=True)


def compile_swift_app(out_binary: Path, arch: str) -> None:
    swift_files = sorted(str(p) for p in MACOS_DIR.glob("*.swift"))
    target = f"{arch}-apple-macosx12.0"
    cmd = ["swiftc", "-O", "-target", target, *swift_files, "-o", str(out_binary)]
    subprocess.run(cmd, check=True)


def create_info_plist(out_plist: Path, version: str) -> None:
    data = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": "MCPBrowser",
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": "com.weydson.mcp-browser",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "MCP Browser",
        "CFBundleDisplayName": "MCP Browser",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 Weydson. Released under the MIT License.",
    }
    with out_plist.open("wb") as fh:
        plistlib.dump(data, fh)


def sign_path(path: Path, identity: str | None) -> None:
    sign_args = ["--force", "--deep"]
    if identity:
        sign_args += ["--options", "runtime", "--sign", identity]
    else:
        sign_args += ["--sign", "-"]
    subprocess.run(["codesign", *sign_args, str(path)], check=True)


def build_app_bundle(
    cli_bundle: Path, target_dir: Path, version: str, arch: str, identity: str | None
) -> Path:
    app_dir = target_dir / "MCP Browser.app"
    macos_dir = app_dir / "Contents" / "MacOS"
    res_dir = app_dir / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    res_dir.mkdir(parents=True)

    compile_swift_app(macos_dir / "MCPBrowser", arch)
    generate_app_icon(res_dir / "AppIcon.icns")
    create_info_plist(app_dir / "Contents" / "Info.plist", version)
    (app_dir / "Contents" / "PkgInfo").write_bytes(b"APPL????")

    shutil.copytree(cli_bundle, res_dir / "mcp-browser", symlinks=True)
    sign_path(app_dir, identity)
    return app_dir


def create_dmg(app_bundle: Path, out_dmg: Path, identity: str | None) -> Path:
    with tempfile.TemporaryDirectory(prefix="mcp-browser-dmg-") as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir()
        shutil.copytree(app_bundle, stage / "MCP Browser.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications")

        out_dmg.parent.mkdir(parents=True, exist_ok=True)
        out_dmg.unlink(missing_ok=True)

        cmd = [
            "hdiutil",
            "create",
            "-volname",
            "MCP Browser",
            "-srcfolder",
            str(stage),
            "-ov",
            "-format",
            "UDZO",
            "-imagekey",
            "zlib-level=9",
            str(out_dmg),
        ]
        subprocess.run(cmd, check=True)
        sign_path(out_dmg, identity)
    return out_dmg


def build_dmg(cli_bundle: Path, out_dir: Path, identity: str | None = None) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("DMG creation is only supported on macOS.")

    from mcp_browser_core import __version__

    arch = current_arch()
    dmg_name = f"mcp-browser-{__version__}-macos-{arch}.dmg"
    out_dmg = out_dir / dmg_name

    with tempfile.TemporaryDirectory(prefix="mcp-browser-app-") as tmp:
        app_dir = build_app_bundle(cli_bundle, Path(tmp), __version__, arch, identity)
        create_dmg(app_dir, out_dmg, identity)

    return out_dmg
