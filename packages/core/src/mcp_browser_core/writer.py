"""Atomic, locked, backed-up writes of client config files."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from filelock import FileLock, Timeout

from .backup import KEEP_BACKUPS, make_backup
from .errors import CommentsWouldBeLost, FileChanged, NotFound, ReadOnly
from .formats import dump, has_comments, indent_unit, load
from .models import Format
from .paths import Paths

ATTEMPTS = 3
__all__ = ["KEEP_BACKUPS", "write_entry"]


class _Retry(Exception):
    """The file changed (or could not be replaced) during this attempt."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Snap(NamedTuple):
    data: bytes
    mtime_ns: int
    ino: int
    mode: int

    @property
    def sig(self) -> tuple[str, int, int]:
        return _digest(self.data), self.mtime_ns, self.ino


def _snapshot(target: Path) -> _Snap | None:
    """Bytes plus identity (mtime, inode) of the file as it is now; None when it does not exist."""
    try:
        with open(target, "rb") as fh:
            st = os.fstat(fh.fileno())
            return _Snap(fh.read(), st.st_mtime_ns, st.st_ino, st.st_mode)
    except FileNotFoundError:
        return None


def _sig(snap: _Snap | None) -> tuple[str, int, int] | None:
    return None if snap is None else snap.sig


def _render(doc: Any, fmt: Format, text: str, existed: bool, bom: bool) -> bytes:
    newline = text.endswith("\n") if existed and text else True
    out = dump(doc, fmt, indent=indent_unit(text), newline=newline)
    crlf = text.count("\r\n")
    if crlf and (fmt != "toml" or crlf >= text.count("\n") - crlf):
        out = re.sub(r"\r?\n", "\r\n", out) if fmt != "toml" else re.sub(r"(?<!\r)\n", "\r\n", out)
    return (("\ufeff" if bom else "") + out).encode("utf-8")


def _denied(target: Path, why: str) -> ReadOnly:
    return ReadOnly(f"{target.name} cannot be written: {why}", path=str(target), reason="permission_denied")


def _attempt(
    target: Path,
    fmt: Format,
    mutate: Callable[[Any], None],
    paths: Paths,
    allow_comment_loss: bool,
    create: bool,
    dedicated_file: bool,
) -> str | None:
    """One read-modify-write pass. Returns the backup path (or None); raises _Retry if the file moved."""
    snap = _snapshot(target)
    existed = snap is not None
    if snap is None and not create:
        raise NotFound(f"{target} does not exist")
    if snap is not None and (not snap.mode & 0o222 or not os.access(target, os.W_OK)):
        raise ReadOnly(
            f"{target.name} is read-only; not overwriting it", path=str(target), reason="read_only"
        )
    data = snap.data if snap else b""
    text = data.decode("utf-8")
    bom = text.startswith("\ufeff")
    text = text.removeprefix("\ufeff")
    if fmt == "jsonc" and has_comments(text, fmt) and not (dedicated_file and allow_comment_loss):
        raise CommentsWouldBeLost(
            f"{target.name} contains comments that rewriting would remove",
            can_override=dedicated_file,
            path=str(target),
        )
    doc = load(text, fmt)
    mutate(doc)
    payload = _render(doc, fmt, text, existed, bom)
    backup: str | None = None
    tmp_name = ""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name[:100]}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        if existed:
            shutil.copymode(target, tmp_name)
        else:
            os.chmod(tmp_name, 0o600)
        if existed:  # back up first (slow), then verify nothing moved right before the swap (fast)
            backup = make_backup(paths, target, data)
        if _sig(_snapshot(target)) != _sig(snap):
            raise _Retry
        os.replace(tmp_name, target)
        return backup
    except _Retry:
        _discard(backup)
        raise
    except FileNotFoundError as exc:  # the file vanished mid-way
        _discard(backup)
        raise _Retry from exc
    except PermissionError as exc:
        _discard(backup)
        raise _denied(target, exc.strerror or "permission denied") from exc
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


def _discard(backup: str | None) -> None:
    if backup:
        Path(backup).unlink(missing_ok=True)


def write_entry(
    path: str,
    fmt: Format,
    mutate: Callable[[Any], None],
    *,
    paths: Paths,
    allow_comment_loss: bool,
    create: bool,
    dedicated_file: bool = True,
) -> str | None:
    """Apply `mutate` to the loaded document and write it back. Returns the backup path, or None
    when the file did not exist. Raises FileChanged / CommentsWouldBeLost."""
    target = Path(os.path.realpath(path))
    paths.locks_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.blake2b(str(target).encode(), digest_size=8).hexdigest()
    try:
        with FileLock(str(paths.locks_dir / f"{key}.lock"), timeout=10):
            for _ in range(ATTEMPTS):
                try:
                    return _attempt(target, fmt, mutate, paths, allow_comment_loss, create, dedicated_file)
                except _Retry:
                    continue
    except Timeout as exc:
        raise FileChanged(f"{target.name} is locked by another mcp-browser operation") from exc
    raise FileChanged(f"{target.name} changed while it was being written; nothing was modified")
