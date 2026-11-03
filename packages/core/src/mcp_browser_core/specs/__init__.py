"""Registry of client specs. Adding a client is one `ClientSpec` row in one of the modules."""

from __future__ import annotations

from . import claude, codex_gemini, editors
from .base import ClientSpec, PathRule

REGISTRY: dict[str, ClientSpec] = {
    spec.id: spec for module in (claude, codex_gemini, editors) for spec in module.SPECS
}

__all__ = ["REGISTRY", "ClientSpec", "PathRule"]
