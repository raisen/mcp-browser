"""Keep secrets out of what the server says: masking of write reports, scrubbing of error text."""

from __future__ import annotations

from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import AddResult, ServerEntry, WriteReport
from mcp_browser_core.scrub import scrubber_for
from mcp_browser_core.secrets import mask_entry


def mask_report(report: WriteReport) -> WriteReport:
    return report.model_copy(update={"entry": mask_entry(report.entry)})


def mask_result(result: AddResult) -> AddResult:
    return result.model_copy(update={"report": mask_report(result.report) if result.report else None})


def scrub(text: str | None, entry: ServerEntry | None) -> str | None:
    """Replace the entry's real (expanded) env/header/arg/URL secrets if a server or library echoed them.
    Core scrubs at the source already; this covers text the server builds itself."""
    if not text or entry is None:
        return text
    return scrubber_for(entry).text(text)


def scrub_catalog(item: CatalogEntry, entry: ServerEntry | None) -> CatalogEntry:
    return item.model_copy(
        update={"error": scrub(item.error, entry), "stderr_tail": scrub(item.stderr_tail, entry)}
    )
