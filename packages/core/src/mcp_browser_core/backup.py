"""Private, pruned backups of a config file's pre-write bytes."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from .paths import Paths

KEEP_BACKUPS = 20
NAME_CHARS = 60
_STAMP = r"\d{8}T\d{12}Z"


def prefix_for(target: Path) -> str:
    """`<hash of the full path>-<readable basename>`: unique per file, short enough for any filesystem."""
    key = hashlib.blake2b(str(target).encode("utf-8", "surrogatepass"), digest_size=8).hexdigest()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", target.name).strip("_")[:NAME_CHARS] or "file"
    return f"{key}-{base}"


def make_backup(paths: Paths, target: Path, data: bytes) -> str:
    """Write `data` into the state dir (0600) and prune old copies of this one file."""
    folder = paths.backups_dir
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    prefix = prefix_for(target)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    dest = folder / f"{prefix}.{stamp}"
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    pattern = re.compile(re.escape(prefix) + r"\." + _STAMP)
    old = sorted(p for p in folder.iterdir() if pattern.fullmatch(p.name))
    for stale in old[:-KEEP_BACKUPS]:
        stale.unlink(missing_ok=True)
    return str(dest)
