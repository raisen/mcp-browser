"""`<state>/catalog.json` cache of what each server exposes, and scanning."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import anyio

from .catalog_models import CatalogEntry
from .connect import ConnectOptions, session
from .errors import AuthRequired, McpBrowserError
from .models import ServerEntry, fingerprint
from .oauth import OAuthHook
from .paths import Paths
from .scrub import scrubber_for


class Catalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, CatalogEntry] = {}

    def load(self) -> None:
        """Read the cache; a missing or damaged file means an empty catalog."""
        self._entries = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for key, raw in data["entries"].items():
                self._entries[key] = CatalogEntry.model_validate(raw)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self._entries = {}

    def get(self, entry_id: str, fingerprint: str) -> CatalogEntry | None:
        """Cached entry only if its fingerprint still matches."""
        found = self._entries.get(entry_id)
        return found if found is not None and found.fingerprint == fingerprint else None

    def put(self, entry: CatalogEntry) -> None:
        self._entries[entry.entry_id] = entry
        self._save()

    def drop(self, entry_id: str) -> None:
        if self._entries.pop(entry_id, None) is not None:
            self._save()

    def all(self) -> list[CatalogEntry]:
        return list(self._entries.values())

    def _save(self) -> None:
        """Atomic: temp file in the same directory, then replace."""
        body = {"entries": {k: json.loads(v.model_dump_json()) for k, v in self._entries.items()}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".catalog-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    async def scan(
        self,
        entries: Sequence[ServerEntry],
        paths: Paths,
        opts: ConnectOptions,
        *,
        limiter: anyio.CapacityLimiter,
        oauth: OAuthHook | None = None,
    ) -> list[CatalogEntry]:
        """Connect to each entry concurrently (bounded by `limiter`); errors are recorded, never raised."""
        results: list[CatalogEntry | None] = [None] * len(entries)

        async def one(i: int, entry: ServerEntry) -> None:
            found = await scan_one(entry, paths, opts, limiter, oauth)
            results[i] = found
            self.put(found)

        async with anyio.create_task_group() as tg:
            for i, entry in enumerate(entries):
                tg.start_soon(one, i, entry)
        return [r for r in results if r is not None]


async def scan_one(
    entry: ServerEntry,
    paths: Paths,
    opts: ConnectOptions,
    limiter: anyio.CapacityLimiter,
    oauth: OAuthHook | None,
) -> CatalogEntry:
    ident, fp, now = entry.id, fingerprint(entry.transport), datetime.now(UTC)
    opts = replace(opts, interactive=False)  # a scan never opens a browser
    try:
        async with session(entry, paths, opts, oauth, limiter=limiter) as s:
            return CatalogEntry(
                entry_id=ident,
                fingerprint=fp,
                scanned_at=now,
                status="ok",
                tools=await s.list_tools(),
                resources=await s.list_resources(),
                prompts=await s.list_prompts(),
                stderr_tail=s.stderr_tail or None,
            )
    except AuthRequired:
        return CatalogEntry(
            entry_id=ident,
            fingerprint=fp,
            scanned_at=now,
            status="needs_auth",
            error="sign-in required",
        )
    except McpBrowserError as exc:
        tail = str(exc.detail.get("stderr_tail") or "") or None
        return CatalogEntry(
            entry_id=ident,
            fingerprint=fp,
            scanned_at=now,
            status="error",
            error=exc.message,
            stderr_tail=tail,
        )
    except Exception as exc:
        err = scrubber_for(entry, home=paths.home).str(str(exc) or type(exc).__name__)
        return CatalogEntry(entry_id=ident, fingerprint=fp, scanned_at=now, status="error", error=err)
