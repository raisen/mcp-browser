"""Release gate: the git tag and all three package versions (and sibling pins) must agree.

python packaging/check_version.py v0.1.0
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("core", "server", "cli")


def problems(tag: str, root: Path = ROOT) -> list[str]:
    expected = tag.removeprefix("v")
    found: list[str] = []
    for name in PACKAGES:
        data = tomllib.loads((root / "packages" / name / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        if project["version"] != expected:
            found.append(f"{project['name']} is {project['version']}, tag says {expected}")
        for dep in project.get("dependencies", []):
            pin = re.fullmatch(r"(mcp-browser(?:-core|-server)?)==(.+)", dep)
            if pin and pin.group(2) != expected:
                found.append(f"{project['name']} pins {dep}, tag says {expected}")
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_version.py vX.Y.Z", file=sys.stderr)
        return 2
    found = problems(sys.argv[1])
    for line in found:
        print(f"version mismatch: {line}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
