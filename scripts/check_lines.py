"""Fail if any tracked or untracked-but-not-ignored source file exceeds the line limit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LIMIT = 250
SUFFIXES = {".py", ".js", ".css", ".html"}
EXCLUDED_PARTS = ("static/vendor/",)
EXCLUDED_NAMES = {"uv.lock"}


def source_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    files: list[Path] = []
    for rel in filter(None, out.split("\0")):
        path = root / rel
        if path.suffix not in SUFFIXES or path.name in EXCLUDED_NAMES or not path.is_file():
            continue
        if any(part in rel.replace("\\", "/") for part in EXCLUDED_PARTS):
            continue
        files.append(path)
    return files


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    bad: list[str] = []
    for path in source_files(root):
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > LIMIT:
            bad.append(f"{path.relative_to(root)}: {count} lines (limit {LIMIT})")
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"ok: all source files <= {LIMIT} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
