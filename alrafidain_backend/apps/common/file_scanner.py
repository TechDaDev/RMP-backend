from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class ScanResult:
    status: str
    details: str = ""


def scan_uploaded_file(file_path: str) -> ScanResult:
    """
    Placeholder scanning boundary.

    Returns:
    - scan_skipped when scanning is disabled.
    - scan_failed when scanning is enabled but backend is not configured.
    """
    if not getattr(settings, "FILE_SCANNING_ENABLED", False):
        return ScanResult(status="scan_skipped", details="File scanning is disabled.")

    if not Path(file_path).exists():
        return ScanResult(status="scan_failed", details="File not found for scanning.")

    backend = getattr(settings, "FILE_SCANNER_BACKEND", "")
    if not backend:
        return ScanResult(
            status="scan_failed",
            details="FILE_SCANNING_ENABLED is true but scanner backend is not configured.",
        )

    return ScanResult(status="scan_clean", details="Placeholder scanner marked file as clean.")
